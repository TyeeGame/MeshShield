import json
from .protocol import REASONS
MAX_LINE = 1536

class Framer:
    def __init__(self):
        self.buffer = bytearray()
        self.dropping = False
        self.errors = 0

    def feed(self, chunk):
        lines = []
        for byte in chunk:
            if byte == 10:
                if not self.dropping:
                    lines.append(bytes(self.buffer))
                self.buffer.clear()
                self.dropping = False
            elif not self.dropping:
                if len(self.buffer) >= MAX_LINE - 1:
                    self.buffer.clear()
                    self.dropping = True
                    self.errors += 1
                else:
                    self.buffer.append(byte)
        return lines

def integer(x, lo=0, hi=0xffffffff):
    return type(x) is int and lo <= x <= hi

def parse_event(line):
    if len(line) >= MAX_LINE:
        raise ValueError('oversized event')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    try:
        e = json.loads(line, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid JSON') from exc
    if not isinstance(e, dict) or type(e.get('v')) is not int or e.get('v') != 1 or not integer(e.get('session'), 1) or not integer(e.get('seq'), 1):
        raise ValueError('invalid envelope')
    kind = e.get('type')
    if kind == 'summary':
        if not integer(e.get('duration_ms'), 1, 60000) or not integer(e.get('last_command_id')) or not integer(e.get('uptime_ms')) or not integer(e.get('log_drops')):
            raise ValueError('invalid summary')
        rows = e.get('nodes')
        if not isinstance(rows, list) or len(rows) != 2 or any(not isinstance(r, dict) for r in rows) or [r.get('node') for r in rows] != [1, 2]:
            raise ValueError('invalid nodes')
        for r in rows:
            keys = ('received', 'allowed', 'blocked', 'transport', 'empty', 'queue_overflow', 'quarantine_ms')
            if any(not integer(r.get(k)) for k in keys) or r['quarantine_ms'] > 60000:
                raise ValueError('invalid counters')
            if r['received'] != r['allowed'] + r['blocked'] or type(r.get('contaminated')) is not bool:
                raise ValueError('inconsistent summary')
            if any(not integer(r.get(k), -1) for k in ('seen_age_ms', 'message_age_ms')):
                raise ValueError('invalid freshness')
            reasons = r.get('reasons')
            if not isinstance(reasons, dict) or set(reasons) != set(REASONS) or any(not integer(v) for v in reasons.values()) or sum(reasons.values()) != r['blocked']:
                raise ValueError('invalid reasons')
    elif kind == 'ack':
        if not integer(e.get('id'), 1) or not integer(e.get('node'), 1, 2) or not integer(e.get('quarantine_ms'), 0, 60000) or not integer(e.get('last_command_id')) or type(e.get('duplicate')) is not bool:
            raise ValueError('invalid acknowledgment')
        if e.get('status') not in ('ok', 'wrong_session', 'invalid_command', 'id_conflict', 'stale_id'):
            raise ValueError('invalid acknowledgment status')
    elif kind == 'telemetry':
        if not integer(e.get('node'), 1, 2) or not integer(e.get('packet_seq')) or not integer(e.get('uptime_ms')) or not integer(e.get('sensor'), -32768, 32767):
            raise ValueError('invalid telemetry')
    elif kind == 'incident':
        if not integer(e.get('node'), 1, 2) or e.get('reason') not in REASONS:
            raise ValueError('invalid incident')
    elif kind == 'error':
        if e.get('reason') not in ('malformed_command', 'command_too_long'):
            raise ValueError('invalid error')
    else:
        raise ValueError('unknown event')
    return e
