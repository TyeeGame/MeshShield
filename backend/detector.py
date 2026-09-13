"""A frozen, learned rate baseline; scores are deviations, never probabilities."""
import math
import statistics

class Detector:
    WINDOW_MS = 5000
    TRAIN_WINDOWS = 12
    SIGMA_FLOOR = 0.25  # messages/second; also absorbs ordinary 1 Hz timing jitter

    def __init__(self, z=3.0):
        self.z = z
        self.training = False
        self.samples = {1: [], 2: []}
        self.baselines = {}
        self.windows = {1: [0, 0], 2: [0, 0]}
        self.streak = {1: 0, 2: 0}
        self.alerts = {}
        self.rates = {}
        self.rejected = {1: 0, 2: 0}

    def reset(self, node=None):
        for n in ([node] if node else (1, 2)):
            self.windows[n] = [0, 0]
            self.streak[n] = 0
            self.alerts.pop(n, None)

    def start(self):
        self.training = True
        self.samples = {1: [], 2: []}
        self.baselines = {}
        self.rejected = {1: 0, 2: 0}
        self.reset()

    def finish(self):
        # Freeze a normal rate and threshold after enough clean training windows.
        if not self.training or any(len(s) < self.TRAIN_WINDOWS for s in self.samples.values()):
            raise ValueError('Need 12 complete clean windows per node (at least 60 seconds).')
        for n, samples in self.samples.items():
            mean = statistics.mean(samples)
            sigma = max(self.SIGMA_FLOOR, statistics.stdev(samples))
            self.baselines[n] = {'mean': mean, 'sigma': sigma, 'threshold': mean + self.z * sigma}
        self.training = False
        self.reset()

    def observe(self, node, duration_ms, row, complete=True):
        # Missing data or blocked traffic would distort the learned normal rate.
        dirty = (not complete or duration_ms < 800 or duration_ms > 1500 or
                 row['seen_age_ms'] < 0 or row['seen_age_ms'] > 2500 or
                 row['transport'] or row['queue_overflow'] or row['contaminated'] or
                 row['quarantine_ms'] or row['blocked'])
        if dirty:
            self.rejected[node] += 1
            self.reset(node)
            return None
        w = self.windows[node]
        w[0] += duration_ms
        w[1] += row['received']
        if w[0] < self.WINDOW_MS:
            return None
        rate = w[1] * 1000 / w[0]
        self.windows[node] = [0, 0]
        self.rates[node] = rate
        if self.training:
            # This demo's known clean mode is ~1 Hz. Refuse training on 4/20 Hz attacks.
            if not 0.4 <= rate <= 1.6:
                self.rejected[node] += 1
                return None
            if len(self.samples[node]) < self.TRAIN_WINDOWS:
                self.samples[node].append(rate)
            if all(len(s) == self.TRAIN_WINDOWS for s in self.samples.values()):
                self.finish()
            return None
        b = self.baselines.get(node)
        if not b:
            return None
        # Require two high-rate windows so one short spike does not trigger an alert.
        self.streak[node] = self.streak[node] + 1 if rate > b['threshold'] else 0
        if self.streak[node] < 2:
            self.alerts.pop(node, None)
            return None
        alert = {'node': node, 'rate': rate, 'baseline': b['mean'], 'threshold': b['threshold'],
                 'score': (rate - b['mean']) / b['sigma'],
                 'reason': f'{rate:.2f} msg/s exceeds learned threshold {b["threshold"]:.2f} in two complete windows'}
        self.alerts[node] = alert
        return alert

    def view(self):
        return {'training': self.training, 'windows': {n: len(s) for n, s in self.samples.items()},
                'required_windows': self.TRAIN_WINDOWS, 'baselines': self.baselines,
                'rejected_intervals': self.rejected, 'sigma_floor': self.SIGMA_FLOOR, 'z': self.z}
