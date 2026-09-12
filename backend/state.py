import time
from collections import deque
from .detector import Detector

class State:
    def __init__(self, mode, clock=time.monotonic, z=3):
        self.mode = mode
        self.clock = clock
        self.session = None
        self.seq = 0
        self.last_event = None
        self.last_summary = None
        self.connected = False
        self.error = None
        self.malformed = 0
        self.log_drops = 0
        self.last_id = 0
        self.gap = True
        self.detector = Detector(z)
        self.auto = False
        self.known_attack = set()
        self.rows = {}
        self.q_until = {1: 0, 2: 0}
        self.pending = {}
        self.commands = deque(maxlen=30)
        self.incidents = deque(maxlen=100)
        self.history = {1: deque(maxlen=120), 2: deque(maxlen=120)}
        self.totals = {n: dict(received=0, allowed=0, blocked=0) for n in (1, 2)}

    def incident(self, node, reason, **fields):
        self.incidents.appendleft(dict(time=time.time(), node=node, reason=reason, **fields))

    def disconnect(self, error='Gateway disconnected'):
        self.connected = False
        self.error = error
        self.gap = True
        self.detector.reset()
        for node in list(self.pending):
            self.fail(node, 'Connection lost; action outcome unknown')

    def fail(self, node, reason):
        p = self.pending.pop(node)
        p['status'] = 'failed'
        p['error'] = reason
        self.incident(node, reason)
        self.detector.reset(node)

    def request(self, node, op, duration_ms=15000, source='manual'):
        if type(node) is not int or node not in (1, 2) or op not in ('quarantine', 'release', 'state'):
            raise ValueError('Invalid node or operation')
        if type(duration_ms) is not int or (not 1 <= duration_ms <= 60000 if op == 'quarantine' else duration_ms != 0):
            raise ValueError('Quarantine duration must be 1–60000 ms; other operations use 0')
        if not self.online() or self.session is None:
            raise ValueError('Wait for a fresh gateway summary')
        if node in self.pending:
            raise ValueError('A command is already pending for this node')
        if self.last_id >= 0xffffffff:
            raise ValueError('Command IDs exhausted; restart gateway')
        self.last_id += 1
        wire = dict(session=self.session, id=self.last_id, op=op, node=node, duration_ms=duration_ms)
        p = dict(wire=wire, status='pending', source=source, attempts=0, sent_at=0,
                 created_at=self.clock(), error=None)
        self.pending[node] = p
        self.commands.appendleft(p)
        # A request invalidates an open rate window, but does not assert quarantine.
        self.detector.reset(node)
        return p

    def online(self):
        return self.connected and self.last_summary is not None and self.clock() - self.last_summary < 3

    def accept(self, e):
        now = self.clock()
        if e['session'] != self.session:
            if e['type'] != 'summary':
                return  # synchronize from a complete gateway state
            self.disconnect('Gateway session changed')
            self.session = e['session']
            self.seq = 0
            self.last_id = 0
            self.rows.clear()
            self.q_until = {1: 0, 2: 0}
            self.totals = {n: dict(received=0, allowed=0, blocked=0) for n in (1, 2)}
            self.detector.reset()
        if e['seq'] <= self.seq:
            return
        if e['seq'] != self.seq + 1 or (self.last_event is not None and now - self.last_event > 3):
            self.gap = True
            self.detector.reset()
        self.seq = e['seq']
        self.last_event = now
        self.connected = True
        self.error = None
        kind = e['type']
        if kind == 'summary':
            self.last_summary = now
            self.last_id = max(self.last_id, e['last_command_id'])
            self.log_drops = e['log_drops']
            for row in e['nodes']:
                n = row['node']
                self.rows[n] = dict(row, at=now, rate=row['received'] * 1000 / e['duration_ms'])
                self.q_until[n] = now + row['quarantine_ms'] / 1000
                for k in self.totals[n]:
                    self.totals[n][k] += row[k]
                self.history[n].append(self.rows[n]['rate'])
                alert = self.detector.observe(n, e['duration_ms'], row, complete=not self.gap and n not in self.pending and not (self.detector.training and n in self.known_attack))
                if alert:
                    if self.detector.streak[n] == 2:
                        self.incident(n, alert['reason'], alert=alert)
                    if self.auto and n not in self.pending:
                        self.request(n, 'quarantine', source='detector')
            self.gap = False
        elif kind == 'ack':
            self.last_id = max(self.last_id, e['last_command_id'])
            n = e['node']
            p = self.pending.get(n)
            if p and p['wire']['id'] == e['id']:
                if e['status'] == 'ok':
                    p['status'] = 'acknowledged'
                    self.pending.pop(n)
                    self.q_until[n] = now + e['quarantine_ms'] / 1000
                    self.detector.reset(n)
                    self.incident(n, f'{p["wire"]["op"]} acknowledged', command_id=e['id'])
                else:
                    self.fail(n, f'Gateway rejected command: {e["status"]}')
        elif kind in ('incident', 'error'):
            self.incident(e.get('node'), e['reason'])

    def tick(self):
        if not self.online():
            self.detector.reset()
            self.gap = True
        for n, p in list(self.pending.items()):
            if self.clock() - p['created_at'] >= 5:
                self.fail(n, 'Acknowledgment timed out; action outcome unknown')

    def view(self):
        now = self.clock()
        online = self.online()
        result = []
        for n in (1, 2):
            row = self.rows.get(n, {})
            age = (now - row['at']) * 1000 if 'at' in row else 1e9
            seen_age = row.get('seen_age_ms', -1)
            fresh = online and seen_age >= 0 and age + seen_age < 2500
            q_ms = max(0, round((self.q_until[n] - now) * 1000))
            pending = self.pending.get(n)
            state = 'HEALTHY'
            if not fresh:
                state = 'OFFLINE'
            elif pending and pending['wire']['op'] == 'quarantine':
                state = 'CONTAINMENT PENDING'
            elif q_ms:
                state = 'QUARANTINED'
            elif n in self.detector.alerts:
                state = 'ANOMALY'
            msg_age = row.get('message_age_ms', -1)
            result.append(dict(node=n, state=state, fresh=fresh, seen_age_ms=None if seen_age < 0 else round(age+seen_age),
                               message_age_ms=None if msg_age < 0 else round(age+msg_age),
                               quarantine_ms=q_ms, totals=self.totals[n], rate=row.get('rate', 0),
                               baseline=self.detector.baselines.get(n), alert=self.detector.alerts.get(n),
                               history=list(self.history[n]), pending=pending,
                               interval={k: v for k, v in row.items() if k != 'at'}))
        return dict(mode=self.mode, gateway_online=online, session=self.session, error=self.error,
                    malformed_lines=self.malformed, log_drops=self.log_drops, auto_containment=self.auto,
                    detector=self.detector.view(), nodes=result, incidents=list(self.incidents), commands=list(self.commands))
