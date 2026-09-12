from collections import deque
from .protocol import validate

class Policy:
    def __init__(self):
        self.tokens = 5.0
        self.last_refill = 0.0
        self.until = 0.0
        self.violations = deque(maxlen=3)

    def remaining(self, now):
        return max(0, round((self.until - now) * 1000))

    def release(self, now):
        self.until = 0
        self.violations.clear()
        self.tokens = 5
        self.last_refill = now

    def expire(self, now):
        if self.until and now >= self.until:
            self.release(now)

    def contain(self, now, duration_ms):
        self.until = now + duration_ms / 1000

    def evaluate(self, data, now):
        self.expire(now)
        reason = validate(data)
        if reason == 'empty':
            return reason
        if self.remaining(now):
            return 'quarantine'
        if reason == 'allowed':
            self.tokens = min(5, self.tokens + (now - self.last_refill) * 5)
            self.last_refill = now
            if self.tokens >= 1:
                self.tokens -= 1
            else:
                reason = 'rate_limit'
        if reason != 'allowed':
            while self.violations and now - self.violations[0] >= 10:
                self.violations.popleft()
            self.violations.append(now)
            if len(self.violations) == 3:
                self.contain(now, 15000)
                self.violations.clear()
        return reason
