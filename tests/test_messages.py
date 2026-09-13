import asyncio
import json
import time
import unittest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.events import parse_event
from backend.messages import MessageHub
from backend.state import State
from simulator.gateway import Gateway


class MessageApiTests(unittest.TestCase):
    def test_lan_can_load_theme_and_font_without_operator_access(self):
        remote = TestClient(create_app(lan_host='192.168.1.20'),
                            client=('192.168.1.30', 12345), base_url='http://192.168.1.20')
        theme = remote.get('/static/theme.css')
        self.assertEqual(theme.status_code, 200)
        self.assertIn('text/css', theme.headers['content-type'])
        font = remote.get('/static/fonts/InterVariable.woff2')
        self.assertEqual(font.status_code, 200)
        self.assertEqual(font.content[:4], b'wOF2')
        self.assertEqual(remote.get('/api/messages/operator').status_code, 403)
        self.assertEqual(remote.get('/static/../backend/app.py').status_code, 403)

    def test_update_lan_address_keeps_codes_and_restricts_access(self):
        app = create_app(lan_host='192.168.1.20')
        local = TestClient(app)
        before = local.get('/api/messages/operator').json()
        response = local.post('/api/messages/lan-address', json={'address': '10.131.10.207'})
        self.assertEqual(response.status_code, 200)
        after = local.get('/api/messages/operator').json()
        self.assertEqual(after['share_url'], 'http://10.131.10.207:80/messages')
        self.assertEqual(after['sender_key'], before['sender_key'])
        self.assertEqual(after['reader_key'], before['reader_key'])
        remote = TestClient(app, client=('10.131.10.208', 12345), base_url='http://10.131.10.207')
        self.assertEqual(remote.get('/messages').status_code, 200)
        self.assertEqual(remote.get('/messages', headers={'host': '192.168.1.20'}).status_code, 403)
        self.assertEqual(remote.post('/api/messages/lan-address', json={'address': '10.0.0.1'}).status_code, 403)
        for invalid in ('127.0.0.1', '0.0.0.0', '224.0.0.1', '255.255.255.255', 'bad', '10.1.1.999'):
            self.assertEqual(local.post('/api/messages/lan-address', json={'address': invalid}).status_code, 422)
        disabled = TestClient(create_app())
        self.assertEqual(disabled.post('/api/messages/lan-address', json={'address': '10.0.0.1'}).status_code, 409)

    def test_relay_allow_deny_and_inbox_isolation(self):
        app = create_app(lan_host='192.168.1.20')
        with TestClient(app) as client:
            deadline = time.monotonic()+4
            while not app.state.messages.ready and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertTrue(app.state.messages.ready)
            operator = client.get('/api/messages/operator').json()
            reader = {'Authorization': 'Bearer '+operator['reader_key']}
            self.assertEqual(client.get('/api/messages/inbox').status_code, 403)
            for _ in range(3):
                denied = client.post('/api/messages/send', json={'text': 'Judge attempt', 'key': ''}).json()
                self.assertEqual(denied['status'], 'blocked')
            self.assertGreater(denied['quarantine_ms'], 0)
            self.assertEqual(client.get('/api/messages/inbox', headers=reader).json()['items'], [])
            allowed = client.post('/api/messages/send', json={'text': '<script>alert(1)</script>', 'key': operator['sender_key']}).json()
            self.assertEqual(allowed['status'], 'delivered')
            self.assertEqual(allowed['source'], 'SIMULATION')
            inbox = client.get('/api/messages/inbox', headers=reader).json()['items']
            self.assertEqual(len(inbox), 1)
            self.assertEqual(inbox[0]['text'], '<script>alert(1)</script>')
            self.assertEqual(client.post('/api/messages/send', json={'text': '🙂'*41}).status_code, 409)
            self.assertEqual(client.post('/api/messages/send', content=b'x'*2049).status_code, 413)
            self.assertEqual(client.get('/messages').status_code, 200)

    def test_remote_cannot_access_operator_even_with_spoofed_host(self):
        app = create_app(lan_host='192.168.1.20')
        remote = TestClient(app, client=('192.168.1.30', 12345), base_url='http://192.168.1.20')
        for path in ('/', '/api/state', '/api/messages/operator', '/docs', '/openapi.json'):
            self.assertEqual(remote.get(path).status_code, 403)
            self.assertEqual(remote.get(path, headers={'host': 'localhost', 'x-forwarded-for': '127.0.0.1'}).status_code, 403)
        self.assertEqual(remote.post('/api/command', json={}).status_code, 403)
        self.assertEqual(remote.get('/messages').status_code, 200)
        self.assertEqual(remote.get('/api/messages/status').status_code, 200)
        self.assertEqual(remote.post('/api/messages/send', json={'text': 'hello'}, headers={'origin': 'http://evil.test'}).status_code, 403)
        self.assertEqual(remote.get('/messages', headers={'host': 'evil.test'}).status_code, 403)
        disabled = TestClient(create_app(), client=('192.168.1.30', 12345))
        self.assertEqual(disabled.get('/messages').status_code, 403)


class MessageCorrelationTests(unittest.IsolatedAsyncioTestCase):
    def test_message_policy_rate_limit_isolation_and_expiry(self):
        gateway = Gateway()
        key = 'ab'*16
        gateway.message(f'K,{gateway.session},1,{key}'.encode())
        mid = 0
        def send(code):
            nonlocal mid
            mid += 1
            return gateway.message(f'M,{gateway.session},{mid},{code},6869'.encode())
        for _ in range(5):
            self.assertEqual(send(key)['reason'], 'allowed')
        for _ in range(3):
            decision = send(key)
            self.assertEqual(decision['reason'], 'rate_limit')
        self.assertEqual(decision['quarantine_ms'], 15000)
        gateway.now = 1
        self.assertEqual(send(key)['reason'], 'quarantine')
        self.assertEqual(send(key)['quarantine_ms'], 14000)
        self.assertEqual(send('00'*16)['reason'], 'unauthorized')
        gateway.now = 15
        self.assertEqual(send(key)['reason'], 'allowed')
        self.assertIsNone(gateway.message(f'M,{gateway.session},{mid},{key},6869'.encode()))

    def setup_hub(self):
        self.state = State('HARDWARE')
        self.hub = MessageHub(self.state)
        self.gateway = Gateway()
        for _ in range(50):
            for event in self.gateway.step():
                self.state.accept(event)
                self.hub.observe(event)
        self.hub.observe(self.gateway.message(self.hub.due()))
        self.assertTrue(self.hub.ready)

    async def test_only_matching_sent_decision_delivers_once(self):
        self.setup_hub()
        task = asyncio.create_task(self.hub.send('hello', self.hub.sender_key))
        await asyncio.sleep(0)
        mid = self.hub.next_id
        decision = dict(type='message_decision', session=self.hub.session, id=mid,
                        slot=1, reason='allowed', quarantine_ms=0)
        self.hub.observe(decision)  # Queued but never written: reject.
        self.assertFalse(task.done())
        self.hub.due()
        self.hub.observe(dict(decision, session=999))
        self.hub.observe(dict(decision, id=mid+100))
        self.assertEqual(len(self.hub.inbox), 0)
        self.hub.observe(decision)
        self.hub.observe(decision)
        self.assertEqual((await task)['status'], 'delivered')
        self.assertEqual(len(self.hub.inbox), 1)

    async def test_disconnect_cancels_delivery_and_requires_handshake(self):
        self.setup_hub()
        task = asyncio.create_task(self.hub.send('never deliver', self.hub.sender_key))
        await asyncio.sleep(0)
        wire = self.hub.due()
        decision = self.gateway.message(wire)
        self.state.disconnect()
        self.hub.disconnect()
        self.hub.observe(decision)
        self.assertEqual((await task)['status'], 'not_delivered')
        self.assertFalse(self.hub.ready)
        self.assertEqual(len(self.hub.inbox), 0)

    async def test_timeout_drops_late_allow(self):
        self.setup_hub()
        task = asyncio.create_task(self.hub.send('late', self.hub.sender_key))
        await asyncio.sleep(0)
        decision = self.gateway.message(self.hub.due())
        self.assertEqual((await task)['status'], 'not_delivered')
        self.hub.observe(decision)
        self.assertEqual(len(self.hub.inbox), 0)

    async def test_old_firmware_and_queue_bound(self):
        self.setup_hub()
        self.hub.supported = self.hub.ready = False
        with self.assertRaises(ValueError):
            await self.hub.send('hello', '')
        self.hub.ready = True
        tasks = [asyncio.create_task(self.hub.send('queued', '')) for _ in range(16)]
        await asyncio.sleep(0)
        with self.assertRaises(ValueError):
            await self.hub.send('overflow', '')
        self.hub.disconnect()
        await asyncio.gather(*tasks)

    def test_event_validation(self):
        event = dict(v=1, session=1, seq=1, type='message_decision', id=1, slot=1,
                     reason='allowed', quarantine_ms=0)
        self.assertEqual(parse_event(json.dumps(event)), event)
        for changes in ({'id': True}, {'slot': 3}, {'reason': 'invented'}, {'quarantine_ms': -1}):
            with self.assertRaises(ValueError):
                parse_event(json.dumps(dict(event, **changes)))
