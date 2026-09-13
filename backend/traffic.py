"""Host-generated endpoints. This module never makes firewall decisions."""
from .protocol import packet

MODES = ('NORMAL', 'UNKNOWN_TYPE', 'FLOOD', 'ANOMALY')

class Traffic:
    def __init__(self):
        self.mode = 'NORMAL'
        self.session = None
        self.deadlines = {1: 0, 2: 0}
        self.seq = {1: 0, 2: 0}

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError('Invalid traffic mode')
        self.mode = mode
        self.deadlines[2] = 0

    def due(self, now, session):
        if session != self.session:
            self.session = session
            self.deadlines = {1: now, 2: now + .2}
            self.seq = {1: 0, 2: 0}
        result = []
        for node in (1, 2):
            if now < self.deadlines[node]:
                continue
            mode = self.mode if node == 2 else 'NORMAL'
            interval = {'FLOOD': .05, 'ANOMALY': .25}.get(mode, 1.0)
            # No catch-up bursts after a stalled/disconnected host.
            self.deadlines[node] = now + interval
            self.seq[node] += 1
            data = packet(kind=127 if mode == 'UNKNOWN_TYPE' else 1,
                          seq=self.seq[node], uptime=int(now*1000))
            result.append(f'T,{session},{node},{data.hex()}\n'.encode('ascii'))
        return result
