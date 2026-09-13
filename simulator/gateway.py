"""Deterministic gateway model; this is never a hardware test."""
import json
import random
import time
from collections import deque
from backend.policy import Policy
from backend.protocol import packet, REASONS
from backend.events import Framer
MODES = ('NORMAL', 'UNKNOWN_TYPE', 'FLOOD', 'ANOMALY')

class Gateway:
    def __init__(self, session=1001):
        self.session = session
        self.seq = 0
        self.last_id = 0
        self.cache = {}
        self.policies = {n: Policy() for n in (1, 2)}
        self.message_policies = {n: Policy() for n in (1, 2)}
        self.message_key = None
        self.last_message_id = 0
        self.modes = {1: 'NORMAL', 2: 'NORMAL'}
        self.connected = {1: True, 2: True}
        self.next_send = {1: 0.5, 2: 0.7}
        self.packet_seq = {1: 0, 2: 0}
        self.last_seen = {1: None, 2: None}
        self.last_message = {1: None, 2: None}
        self.last_sample = {1: -1, 2: -1}
        self.rows = {n: self.fresh(n) for n in (1, 2)}
        self.now = 0.0
        self.last_summary = 0.0
        self.rng = random.Random(42)

    @staticmethod
    def fresh(n):
        return dict(node=n, received=0, allowed=0, blocked=0, transport=0, empty=0,
                    queue_overflow=0, quarantine_ms=0, contaminated=False,
                    seen_age_ms=-1, message_age_ms=-1, reasons={r: 0 for r in REASONS})

    def event(self, kind, **fields):
        self.seq += 1
        return dict(v=1, session=self.session, seq=self.seq, type=kind, **fields)

    def command(self, c):
        if not isinstance(c, dict) or set(c) != {'session', 'id', 'op', 'node', 'duration_ms'}:
            return self.event('error', reason='malformed_command')
        n, cid, op, duration = c['node'], c['id'], c['op'], c['duration_ms']
        valid = (type(n) is int and n in (1, 2) and type(cid) is int and 0 < cid <= 0xffffffff and
                 type(duration) is int and op in ('quarantine', 'release', 'state') and
                 (1 <= duration <= 60000 if op == 'quarantine' else duration == 0))
        status, duplicate = 'ok', False
        if c['session'] != self.session:
            status = 'wrong_session'
        elif not valid:
            status = 'invalid_command'
        elif cid <= self.last_id:
            duplicate = True
            status = ('ok' if self.cache[cid] == c else 'id_conflict') if cid in self.cache else 'stale_id'
        else:
            if op == 'quarantine':
                self.policies[n].contain(self.now, duration)
                self.rows[n]['contaminated'] = True
            elif op == 'release':
                self.policies[n].release(self.now)
            self.last_id = cid
            self.cache[cid] = dict(c)
            if len(self.cache) > 16:
                del self.cache[min(self.cache)]
        return self.event('ack', id=cid, node=n, status=status, duplicate=duplicate,
                          quarantine_ms=self.policies[n].remaining(self.now) if n in (1, 2) else 0,
                          last_command_id=self.last_id)

    def message(self, line):
        try:
            parts = line.decode('ascii').strip().split(',')
            if parts[0] not in ('K', 'M') or int(parts[1]) != self.session:
                raise ValueError()
            mid = int(parts[2])
            if not 1 <= mid <= 0xffffffff or len(parts[3]) != 32:
                raise ValueError()
            key = bytes.fromhex(parts[3])
            if parts[0] == 'K' and len(parts) == 4:
                self.message_key = key
                self.last_message_id = 0
                return self.event('message_ready', id=mid)
            if len(parts) != 5 or not 1 <= len(bytes.fromhex(parts[4])) <= 160 or self.message_key is None:
                raise ValueError()
            if mid <= self.last_message_id:
                return None
            self.last_message_id = mid
            n = 1 if key == self.message_key else 2
            policy = self.message_policies[n]
            reason = policy.evaluate(packet(kind=1 if n == 1 else 127), self.now)
            return self.event('message_decision', id=mid, slot=n,
                              reason='unauthorized' if reason == 'unknown_type' else reason,
                              quarantine_ms=policy.remaining(self.now))
        except (ValueError, IndexError, UnicodeError):
            return self.event('error', reason='malformed_command')

    def step(self, dt=0.02):
        self.now = round(self.now + dt, 8)
        events = []
        for n in (1, 2):
            p, row = self.policies[n], self.rows[n]
            p.expire(self.now)
            row['contaminated'] |= bool(p.remaining(self.now))
            if not self.connected[n]:
                row['transport'] += 1
                continue
            self.last_seen[n] = self.now
            if self.now + 1e-8 < self.next_send[n]:
                row['empty'] += 1
                continue
            mode = self.modes[n]
            self.packet_seq[n] += 1
            data = packet(kind=127 if mode == 'UNKNOWN_TYPE' else 1,
                          seq=self.packet_seq[n], uptime=int(self.now * 1000))
            # Schedule from the intended deadline so 50 ms doesn't round to 60 ms.
            interval = {'FLOOD': .05, 'ANOMALY': .25}.get(mode, 1 + self.rng.uniform(-.04, .04))
            self.next_send[n] += interval
            if self.next_send[n] < self.now:
                self.next_send[n] = self.now + interval
            reason = p.evaluate(data, self.now)
            row['received'] += 1
            self.last_message[n] = self.now
            if reason == 'allowed':
                row['allowed'] += 1
                if self.now - self.last_sample[n] >= 1:
                    events.append(self.event('telemetry', node=n, packet_seq=self.packet_seq[n], uptime_ms=int(self.now*1000), sensor=2200))
                    self.last_sample[n] = self.now
            else:
                row['blocked'] += 1
                row['reasons'][reason] += 1
                if row['blocked'] <= 3:
                    events.append(self.event('incident', node=n, reason=reason))
            row['contaminated'] |= bool(p.remaining(self.now))
        if self.now - self.last_summary >= 1 - 1e-8:
            rows = []
            for n in (1, 2):
                row = self.rows[n]
                row['quarantine_ms'] = self.policies[n].remaining(self.now)
                row['seen_age_ms'] = -1 if self.last_seen[n] is None else round((self.now-self.last_seen[n])*1000)
                row['message_age_ms'] = -1 if self.last_message[n] is None else round((self.now-self.last_message[n])*1000)
                rows.append(row)
                self.rows[n] = self.fresh(n)
            events.append(self.event('summary', messages=1, duration_ms=round((self.now-self.last_summary)*1000), uptime_ms=round(self.now*1000), log_drops=0, last_command_id=self.last_id, nodes=rows))
            self.last_summary = self.now
        return events

class SimTransport:
    def __init__(self):
        self.gateway = Gateway(random.SystemRandom().randint(1, 0x7fffffff))
        self.out = deque()
        self.framer = Framer()
        self.last_step = time.monotonic()

    def read(self):
        time.sleep(.01)
        now = time.monotonic()
        steps = min(50, int((now - self.last_step) / .02))
        for _ in range(steps):
            for event in self.gateway.step():
                self.out.append(json.dumps(event, separators=(',', ':')).encode() + b'\n')
            self.last_step += .02
        return self.out.popleft() if self.out else b''

    def write(self, data):
        for line in self.framer.feed(data):
            event = self.gateway.message(line) if line.startswith((b'K,', b'M,')) else self.gateway.command(json.loads(line))
            if event:
                self.out.append(json.dumps(event).encode() + b'\n')

    def close(self):
        pass
