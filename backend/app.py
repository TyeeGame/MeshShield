import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from .state import State
from .transport import Bridge, SerialTransport
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


def create_app(simulate=True, port=None, z=3.0):
    if not simulate and not port:
        raise ValueError('Hardware mode requires an explicit --port')
    state = State('SIMULATION' if simulate else 'HARDWARE', z=z)
    factory = SimTransport if simulate else lambda: SerialTransport(port)
    bridge = Bridge(state, factory)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(bridge.run())
        yield
        await bridge.stop()
        await task

    app = FastAPI(title='MeshShield', lifespan=lifespan)
    app.state.mesh = state
    app.state.bridge = bridge

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        # Local service: reject foreign browser origins and DNS-rebinding hosts.
        host = request.headers.get('host', '').split(':')[0]
        if host not in ('localhost', '127.0.0.1', 'testserver'):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Localhost only'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Same origin required'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        return response

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
