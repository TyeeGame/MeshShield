import asyncio
import json
import logging
import time
from .events import Framer, parse_event
LOG = logging.getLogger(__name__)

class SerialTransport:
    def __init__(self, port):
        import serial
        self.serial = serial.Serial(port, 115200, timeout=.05, write_timeout=.2)

    def read(self):
        return self.serial.read(min(max(self.serial.in_waiting, 1), 2048))

    def write(self, data):
        if self.serial.write(data) != len(data):
            raise OSError('Partial USB write')

    def close(self):
        self.serial.close()

class Bridge:
    """One owner serializes every write. API handlers only enqueue bounded commands."""
    def __init__(self, state, factory):
        self.state = state
        self.factory = factory
        self.transport = None
        self.running = True
        self.framer = Framer()

    async def run(self):
        while self.running:
            try:
                if self.transport is None:
                    self.transport = await asyncio.to_thread(self.factory)
                    self.framer = Framer()
                chunk = await asyncio.to_thread(self.transport.read)
                lines = self.framer.feed(chunk)
                if self.framer.errors:
                    self.state.malformed += self.framer.errors
                    self.state.gap = True
                    self.framer.errors = 0
                for line in lines:
                    try:
                        self.state.accept(parse_event(line))
                    except (ValueError, TypeError, KeyError) as exc:
                        self.state.malformed += 1
                        self.state.gap = True
                        LOG.debug('Rejected serial event: %s', exc)
                self.state.tick()
                # Iteration snapshot: acknowledgments are handled on the next read.
                for p in list(self.state.pending.values()):
                    now = self.state.clock()
                    if p['attempts'] < 3 and (p['attempts'] == 0 or now - p['sent_at'] >= 1):
                        payload = json.dumps(p['wire'], separators=(',', ':')).encode() + b'\n'
                        await asyncio.to_thread(self.transport.write, payload)
                        p['attempts'] += 1
                        p['sent_at'] = now
            except (OSError, IOError) as exc:
                self.state.disconnect(str(exc))
                if self.transport:
                    self.transport.close()
                    self.transport = None
                await asyncio.sleep(1)
        if self.transport:
            self.transport.close()
            self.transport = None

    async def stop(self):
        self.running = False
