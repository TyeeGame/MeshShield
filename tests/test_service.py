import asyncio
import json
import time
import unittest
from collections import deque
try:
    import httpx
    from fastapi.testclient import TestClient
    from backend.app import create_app
    SERVICE_AVAILABLE = True
except ImportError:
    SERVICE_AVAILABLE = False
from backend.state import State
from backend.transport import Bridge
from simulator.gateway import Gateway

@unittest.skipUnless(SERVICE_AVAILABLE, 'Install requirements-dev.txt for HTTP tests')
class ApiTests(unittest.TestCase):
    def test_api_simulation_ack_and_validation(self):
        app=create_app()
        with TestClient(app) as client:
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                state=client.get('/api/state').json()
                if state['gateway_online']:break
                time.sleep(.03)
            self.assertTrue(state['gateway_online'])
            self.assertEqual(state['mode'],'SIMULATION')
            self.assertEqual(client.get('/').status_code,200)
            self.assertIn('text/html',client.get('/').headers['content-type'])
            self.assertEqual(client.get('/static/app.js').status_code,200)
            self.assertEqual(client.post('/api/command',json={'node':3,'op':'quarantine'}).status_code,422)
            self.assertEqual(client.post('/api/command',json={'node':True,'op':'quarantine'}).status_code,422)
            self.assertEqual(client.post('/api/command',json={'node':2,'op':'release','duration_ms':1}).status_code,409)
            result=client.post('/api/command',json={'node':2,'op':'quarantine','duration_ms':15000})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json()['status'],'pending')
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                state=client.get('/api/state').json()
                if state['commands'][0]['status']=='acknowledged':break
                time.sleep(.02)
            self.assertEqual(state['nodes'][1]['state'],'QUARANTINED')
            self.assertEqual(client.post('/api/training/start').status_code,409)
            self.assertEqual(client.post('/api/simulation/mode',json={'mode':'ANOMALY'}).status_code,200)
            self.assertEqual(client.post('/api/auto',json={'enabled':True}).status_code,200)
            self.assertEqual(client.post('/api/auto',json={'enabled':False},headers={'origin':'https://elsewhere.example'}).status_code,403)
            self.assertEqual(client.get('/api/state',headers={'host':'evil.example'}).status_code,403)

    def test_hardware_no_attack_control_and_missing_port(self):
        with self.assertRaises(ValueError):create_app(simulate=False)
        app=create_app(simulate=False,port='UNUSED')
        # No lifespan means no hardware is opened in this API-only test.
        client=TestClient(app)
        self.assertEqual(client.post('/api/simulation/mode',json={'mode':'FLOOD'}).status_code,409)
        self.assertEqual(client.get('/api/state').json()['mode'],'HARDWARE')
        self.assertEqual(client.post('/api/command',json={'node':1,'op':'quarantine'}).status_code,409)

    def test_hardware_mode_selector_controls_host_source(self):
        app=create_app(simulate=False,port='UNUSED')
        app.state.bridge.transport=object()  # No actual port is opened.
        gateway=Gateway()
        for _ in range(50):
            for event in gateway.step():
                if event['type']=='summary':event['ingress']='usb_virtual'
                app.state.mesh.accept(event)
        client=TestClient(app)  # No lifespan: the hardware transport stays unopened.
        response=client.post('/api/traffic/mode',json={'mode':'ANOMALY'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(app.state.bridge.traffic.mode,'ANOMALY')
        self.assertEqual(client.get('/api/state').json()['traffic_mode'],'ANOMALY')
        self.assertEqual(client.post('/api/training/start').status_code,409)

class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def test_reconnect_requires_new_summary(self):
        state = State('HARDWARE')
        gateway = Gateway()
        for _ in range(50):
            for event in gateway.step():
                if event['type'] == 'summary':
                    event['ingress'] = 'usb_virtual'
                state.accept(event)
        self.assertTrue(state.online())
        state.disconnect()
        state.accept(dict(session=state.session, seq=state.seq + 1,
                          type='telemetry', node=1))
        self.assertFalse(state.online())
        self.assertIsNone(state.ingress)
        for _ in range(100):
            for event in gateway.step():
                if event['type'] == 'summary':
                    event['ingress'] = 'usb_virtual'
                state.accept(event)
        self.assertTrue(state.online())
        self.assertEqual(state.ingress, 'usb_virtual')

    async def test_hardware_generates_traffic_only_after_firmware_handshake(self):
        g=Gateway()
        class Fake:
            def __init__(self):self.new_firmware=False;self.writes=[]
            def read(self):
                time.sleep(.005)
                events=g.step(.02)
                for e in events:
                    if e['type']=='summary' and self.new_firmware:e['ingress']='usb_virtual'
                return b''.join(json.dumps(e).encode()+b'\n' for e in events)
            def write(self,data):self.writes.append(data)
            def close(self):pass
        device=Fake();state=State('HARDWARE');bridge=Bridge(state,lambda:device)
        task=asyncio.create_task(bridge.run())
        try:
            deadline=time.monotonic()+3
            while not state.online() and time.monotonic()<deadline:await asyncio.sleep(.01)
            self.assertTrue(state.online())
            self.assertEqual(device.writes,[])
            device.new_firmware=True
            bridge.traffic.set_mode('UNKNOWN_TYPE')
            deadline=time.monotonic()+3
            while len(device.writes)<2 and time.monotonic()<deadline:await asyncio.sleep(.01)
            self.assertGreaterEqual(len(device.writes),2)
            from backend.protocol import validate
            packets={}
            for line in device.writes:
                prefix,session,node,data=line.decode().strip().split(',')
                self.assertEqual(prefix,'T')
                self.assertEqual(int(session),g.session)
                packets[int(node)]=validate(bytes.fromhex(data))
            self.assertEqual(packets,{1:'allowed',2:'unknown_type'})
        finally:
            await bridge.stop();await task

    async def test_malformed_disconnect_reconnect_and_retry_same_id(self):
        g=Gateway()
        initial=[e for _ in range(50) for e in g.step()]
        class Fake:
            def __init__(self, fail=False):
                self.data=deque([b'not json\n', b'x'*1800+b'\n']+[json.dumps(e).encode()+b'\n' for e in initial])
                self.writes=[]
                self.fail=fail
                self.closed=False
            def read(self):
                time.sleep(.002)
                if self.data:return self.data.popleft()
                if self.fail:
                    self.fail=False
                    raise OSError('Unplugged')
                return b''
            def write(self,data):self.writes.append(data)
            def close(self):self.closed=True
        first,second=Fake(True),Fake()
        transports=iter([first,second])
        state=State('HARDWARE')
        bridge=Bridge(state,lambda:next(transports))
        task=asyncio.create_task(bridge.run())
        try:
            deadline=time.monotonic()+3
            while time.monotonic()<deadline and bridge.transport is not second:await asyncio.sleep(.01)
            # A reconnect must carry newer event sequences, not replay the old summary.
            second.data.extend(json.dumps(e).encode()+b'\n' for _ in range(50) for e in g.step())
            deadline=time.monotonic()+2
            while time.monotonic()<deadline and not state.online():await asyncio.sleep(.01)
            self.assertTrue(first.closed)
            self.assertTrue(state.online())
            self.assertGreaterEqual(state.malformed,4)
            state.request(2,'quarantine')
            deadline=time.monotonic()+2
            while time.monotonic()<deadline and len(second.writes)<2:await asyncio.sleep(.02)
            self.assertEqual(len(second.writes),2)
            self.assertEqual(second.writes[0],second.writes[1])
            self.assertLess(len(second.writes[0]),256)
        finally:
            await bridge.stop()
            await task
        self.assertTrue(second.closed)

if __name__=='__main__':unittest.main()
