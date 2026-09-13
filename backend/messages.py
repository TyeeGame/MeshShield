"""Bounded message relay. Only matched gateway allow events enter the inbox."""
import asyncio
import secrets
import time
from collections import deque


class MessageHub:
    def __init__(self, state):
        self.state = state
        # Sending and reading use different codes. Both change on backend restart.
        self.sender_key = secrets.token_hex(16)
        self.reader_key = secrets.token_urlsafe(24)
        self.pending = {}
        self.inbox = deque(maxlen=50)
        self.audit = deque(maxlen=50)
        self.next_id = 0
        self.session = None
        self.config_id = None
        self.ready = False
        self.attempts = 0
        self.sent_at = 0
        self.supported = False

    def disconnect(self):
        # Never deliver queued text after losing contact with the gateway.
        self.ready = self.supported = False
        self.session = self.config_id = None
        self.attempts = 0
        for item in self.pending.values():
            if not item['future'].done():
                item['future'].set_result({'status': 'not_delivered', 'reason': 'Gateway disconnected'})
        self.pending.clear()

    def observe(self, event):
        if event['type'] == 'summary':
            if self.session != event['session']:
                self.disconnect()
                self.session = event['session']
            self.supported = type(event.get('messages')) is int and event['messages'] == 1
            if not self.supported:
                self.ready = False
        elif event['session'] == self.session and event['type'] == 'message_ready':
            if event['id'] == self.config_id:
                self.ready = True
        elif event['session'] == self.session and event['type'] == 'message_decision':
            # Match the reply to a message we actually sent in this gateway session.
            item = self.pending.get(event['id'])
            if not item or not item['sent'] or item['future'].done():
                return
            self.pending.pop(event['id'])
            result = dict(status='delivered' if event['reason'] == 'allowed' else 'blocked',
                          reason=event['reason'], slot=event['slot'],
                          quarantine_ms=event['quarantine_ms'], id=event['id'],
                          source=self.state.mode, time=time.time())
            if result['status'] == 'delivered':
                # This is the only place that adds text to the partner's inbox.
                self.inbox.appendleft(dict(result, text=item['text']))
            self.audit.appendleft(result)
            item['future'].set_result(result)

    def due(self):
        if not self.state.online():
            self.disconnect()
            return None
        if not self.supported:
            return None
        now = self.state.clock()
        if not self.ready:
            # K installs the sender code over USB before any messages are sent.
            if self.attempts < 3 and (not self.attempts or now-self.sent_at >= 1):
                if self.config_id is None:
                    self.config_id = secrets.randbelow(0xffffffff) + 1
                self.attempts += 1
                self.sent_at = now
                return f'K,{self.session},{self.config_id},{self.sender_key}\n'.encode('ascii')
            return None
        for mid, item in self.pending.items():
            # Send each message once; a retry could deliver the same text twice.
            if not item['sent'] and not item['future'].done():
                item['sent'] = True
                return f'M,{self.session},{mid},{item["key"]},{item["text"].encode("utf-8").hex()}\n'.encode('ascii')
        return None

    async def send(self, text, key):
        if not text.strip() or len(text.encode('utf-8')) > 160:
            raise ValueError('Use 1–160 UTF-8 bytes of message text')
        if not self.ready or not self.state.online():
            raise ValueError('Gateway unavailable or message firmware not ready')
        if len(self.pending) >= 16:
            raise ValueError('Message queue full; try again shortly')
        if self.next_id >= 0xffffffff:
            raise ValueError('Message IDs exhausted; restart backend')
        # Normalize malformed credentials, but let the gateway decide authorization.
        if len(key) != 32 or any(c not in '0123456789abcdefABCDEF' for c in key):
            key = '0' * 32
        self.next_id += 1
        mid = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[mid] = dict(text=text, key=key.lower(), future=future, sent=False)
        try:
            return await asyncio.wait_for(future, timeout=5)
        except asyncio.TimeoutError:
            return {'status': 'not_delivered', 'reason': 'Argon decision timed out; message was not delivered'}
        finally:
            self.pending.pop(mid, None)

    def status(self):
        return dict(ready=self.ready and self.state.online(), mode=self.state.mode,
                    supported=self.supported, pending=len(self.pending))
