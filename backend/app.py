import asyncio
import secrets
import ipaddress
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from .state import State
from .transport import Bridge, SerialTransport
from .messages import MessageHub
from simulator.gateway import SimTransport, MODES
DASHBOARD = Path(__file__).resolve().parents[1] / 'dashboard'

class CommandRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    node: StrictInt = Field(ge=1, le=2)
    op: Literal['quarantine', 'release', 'state']
    duration_ms: StrictInt = Field(default=15000, ge=0, le=60000)

class AutoRequest(BaseModel):
    enabled: bool

class ModeRequest(BaseModel):
    mode: Literal['NORMAL', 'UNKNOWN_TYPE', 'FLOOD', 'ANOMALY']

class MessageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=160)
    key: str = Field(default='', max_length=64)

class LanAddressRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    address: str = Field(min_length=1, max_length=15)


def create_app(simulate=True, port=None, z=3.0, lan_host=None):
    if not simulate and not port:
        raise ValueError('Hardware mode requires an explicit --port')
    state = State('SIMULATION' if simulate else 'HARDWARE', z=z)
    factory = SimTransport if simulate else lambda: SerialTransport(port)
    bridge = Bridge(state, factory)
    # Web requests queue messages; the bridge owns the USB connection.
    messages = MessageHub(state)
    bridge.messages = messages

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(bridge.run())
        yield
        await bridge.stop()
        await task

    app = FastAPI(title='MeshShield', lifespan=lifespan)
    app.state.mesh = state
    app.state.bridge = bridge
    app.state.messages = messages

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        # Local service: reject foreign browser origins and DNS-rebinding hosts.
        host = request.headers.get('host', '').split(':')[0]
        if host not in ('localhost', '127.0.0.1', 'testserver', lan_host):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Localhost only'}, status_code=403)
        local = request.client is not None and request.client.host in ('127.0.0.1', '::1', 'testclient')
        # Partners can use the message page, but cannot change operator settings.
        public_paths = {'/messages', '/static/messages.js', '/static/messages.css',
                        '/api/messages/status', '/api/messages/send', '/api/messages/inbox'}
        if not local and (not lan_host or request.url.path not in public_paths):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Operator controls are local only'}, status_code=403)
        if request.url.path == '/api/messages/send':
            # Bound the body before JSON parsing, including chunked requests.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 2048:
                    from fastapi.responses import JSONResponse
                    return JSONResponse({'detail': 'Message request too large'}, status_code=413)
            request._body = bytes(body)
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Same origin required'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/messages')
    async def message_page():
        return FileResponse(DASHBOARD / 'messages.html')

    @app.get('/api/messages/status')
    async def message_status():
        return messages.status()

    @app.get('/api/messages/operator')
    async def message_operator(request: Request):
        port_number = request.url.port or 80
        return dict(messages.status(), sender_key=messages.sender_key,
                    reader_key=messages.reader_key, audit=list(messages.audit),
                    lan_host=lan_host,
                    share_url=f'http://{lan_host}:{port_number}/messages' if lan_host else None)

    @app.post('/api/messages/lan-address')
    async def update_lan_address(c: LanAddressRequest):
        nonlocal lan_host
        if not lan_host:
            raise HTTPException(409, 'Start the backend with --lan-host first to enable LAN sharing')
        try:
            address = ipaddress.IPv4Address(c.address.strip())
            if (address.is_loopback or address.is_unspecified or address.is_multicast or
                    address.is_reserved or int(address) == 0xffffffff):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'Enter your laptop’s Wi-Fi IPv4 address, without http:// or a port')
        lan_host = str(address)
        return {'lan_host': lan_host}

    @app.post('/api/messages/send')
    async def send_message(c: MessageRequest):
        try:
            return await messages.send(c.text, c.key)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get('/api/messages/inbox')
    async def message_inbox(request: Request):
        # The inbox code only grants read access, not permission to send.
        supplied = request.headers.get('authorization', '')
        if not secrets.compare_digest(supplied, 'Bearer ' + messages.reader_key):
            raise HTTPException(403, 'Enter the inbox code provided by the operator')
        return dict(messages.status(), items=list(messages.inbox))

    @app.get('/api/state')
    async def get_state():
        view = state.view()
        if simulate and bridge.transport:
            view['simulation_mode'] = bridge.transport.gateway.modes[2]
        view['traffic_mode'] = view.get('simulation_mode', bridge.traffic.mode)
        return view

    @app.post('/api/command')
    async def command(c: CommandRequest):
        try:
            return state.request(c.node, c.op, c.duration_ms)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/training/start')
    async def start_training():
        if not state.online() or any(p for p in state.pending.values()) or any(r['state'] != 'HEALTHY' for r in state.view()['nodes']):
            raise HTTPException(409, 'Both nodes must be healthy, online, and in NORMAL mode')
        if (simulate and bridge.transport and bridge.transport.gateway.modes[2] != 'NORMAL') or (not simulate and bridge.traffic.mode != 'NORMAL'):
            raise HTTPException(409, 'Set virtual device 2 to NORMAL before training')
        state.detector.start()
        state.gap = True
        state.incident(None, 'Clean baseline training started; keep both nodes NORMAL')
        return state.detector.view()

    @app.post('/api/training/finish')
    async def finish_training():
        try:
            state.detector.finish()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return state.detector.view()

    @app.post('/api/auto')
    async def auto(c: AutoRequest):
        state.auto = c.enabled
        return {'enabled': state.auto}

    @app.post('/api/traffic/mode')
    @app.post('/api/simulation/mode')
    async def mode(c: ModeRequest):
        if not simulate and (not state.online() or state.ingress != 'usb_virtual'):
            raise HTTPException(409, 'Connect the USB-only Argon firmware first')
        if bridge.transport is None:
            raise HTTPException(409, 'Simulator is starting')
        # Bridge reads run in one thread, assignment is an atomic setting update.
        if simulate:
            bridge.transport.gateway.modes[2] = c.mode
        else:
            bridge.traffic.set_mode(c.mode)
        state.known_attack = {2} if c.mode != 'NORMAL' else set()
        if state.detector.training:
            state.detector.reset(2)
            state.gap = True
        return {'mode': c.mode}

    @app.get('/')
    async def index():
        return FileResponse(DASHBOARD / 'index.html')

    app.mount('/static', StaticFiles(directory=DASHBOARD), name='static')
    return app
