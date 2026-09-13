import json
import unittest
from backend.protocol import packet, validate
from backend.policy import Policy
from backend.events import Framer, parse_event
from backend.detector import Detector
from backend.state import State
from simulator.gateway import Gateway

class ProtocolTests(unittest.TestCase):
    def test_crc_vector_and_invalid(self):
        import binascii
        self.assertEqual(binascii.crc_hqx(b'123456789', 0xffff), 0x29b1)
        self.assertEqual(packet(seq=1, uptime=1000).hex(), '010101000000e8030000980800000000541e')
        for data, reason in [(b'no', 'malformed'), (packet()[:-1]+b'\0', 'checksum'),
                             (packet(version=2), 'version'), (packet(kind=127), 'unknown_type'),
                             (packet(kind=0), 'empty')]:
            self.assertEqual(validate(data), reason)

    def test_malformed_lines_and_recovery(self):
        f = Framer()
        self.assertEqual(f.feed(b'x'*2000+b'\n{}\n'), [b'{}'])
        self.assertEqual(f.errors, 1)
        for line in (b'{}', b'not json', b'\xff', b'{"v":1,"v":2}'):
            with self.assertRaises(ValueError): parse_event(line)
        gateway = Gateway()
        events = [e for _ in range(50) for e in gateway.step()]
        for e in events:
            self.assertEqual(parse_event(json.dumps(e).encode()), e)
        summary = events[-1]
        summary['nodes'][0]['received'] = True
        with self.assertRaises(ValueError): parse_event(json.dumps(summary).encode())

class PolicyTests(unittest.TestCase):
    def test_bucket_and_expiry_without_extension(self):
        p = Policy()
        for _ in range(5): self.assertEqual(p.evaluate(packet(), 0), 'allowed')
        for t in (.01, .02, .03): self.assertEqual(p.evaluate(packet(), t), 'rate_limit')
        expiry = p.until
        for t in (1, 3, 10, 14): self.assertEqual(p.evaluate(packet(), t), 'quarantine')
        self.assertEqual(p.until, expiry)
        self.assertEqual(p.evaluate(packet(), expiry), 'allowed')
        self.assertFalse(p.violations)

    def test_refill_rolling_and_empty(self):
        p = Policy()
        for i in range(100): self.assertEqual(p.evaluate(packet(), i*.25), 'allowed')
        self.assertEqual(p.evaluate(packet(kind=0), 25), 'empty')
        p = Policy()
        for t in (0, 11, 22): p.evaluate(packet(kind=127), t)
        self.assertEqual(p.until, 0)
        p.evaluate(b'', 22.1)
        p.evaluate(packet(version=2), 22.2)
        self.assertGreater(p.until, 22)

    def test_flood_isolation(self):
        g = Gateway(); g.modes[2] = 'FLOOD'
        summaries = [e for _ in range(1000) for e in g.step() if e['type']=='summary']
        self.assertGreater(sum(e['nodes'][0]['allowed'] for e in summaries), 17)
        self.assertEqual(sum(e['nodes'][0]['blocked'] for e in summaries), 0)
        self.assertGreater(sum(e['nodes'][1]['blocked'] for e in summaries), 200)
        self.assertTrue(any(e['nodes'][1]['quarantine_ms'] for e in summaries))

    def test_idempotent_commands_and_old_ids(self):
        g = Gateway()
        c = dict(session=g.session, id=1, op='quarantine', node=2, duration_ms=15000)
        self.assertEqual(g.command(c)['status'], 'ok')
        g.step(3)
        self.assertEqual(g.command(c)['quarantine_ms'], 12000)
        self.assertEqual(g.command(dict(c, duration_ms=10000))['status'], 'id_conflict')
        for i in range(2, 20): g.command(dict(c, id=i, op='state', duration_ms=0))
        self.assertEqual(g.command(c)['status'], 'stale_id')
        self.assertEqual(g.policies[2].until, 15)
        self.assertEqual(g.command(dict(c, id=20, duration_ms=60001))['status'], 'invalid_command')
        self.assertEqual(g.command(dict(c, id=20, session=999))['status'], 'wrong_session')

class DetectorTests(unittest.TestCase):
    @staticmethod
    def row(n=1, rate=1, **changes):
        return dict(Gateway.fresh(n), received=rate, allowed=rate, seen_age_ms=0, **changes)

    def trained(self):
        d=Detector();d.start()
        for _ in range(60):
            for n in (1,2): d.observe(n,1000,self.row(n))
        self.assertFalse(d.training)
        return d

    def test_clean_training_held_out_and_anomaly(self):
        d=self.trained()
        self.assertEqual(d.baselines[1]['threshold'],1.75)
        for _ in range(40): self.assertIsNone(d.observe(1,1000,self.row()))
        for _ in range(9): self.assertIsNone(d.observe(1,1000,self.row(rate=4)))
        alert=d.observe(1,1000,self.row(rate=4))
        self.assertEqual(alert['rate'],4)
        self.assertIn('two complete windows',alert['reason'])
        self.assertEqual(d.baselines[1]['mean'],1)

    def test_incomplete_disconnect_and_quarantine_windows(self):
        d=self.trained()
        for _ in range(4): d.observe(1,1000,self.row(rate=4))
        d.observe(1,1000,self.row(rate=4),complete=False)
        self.assertEqual(d.windows[1],[0,0])
        for _ in range(5): d.observe(1,1000,self.row(rate=4))
        self.assertEqual(d.streak[1],1)
        row=self.row(rate=4);row['contaminated']=True
        d.observe(1,1000,row)
        self.assertEqual(d.streak[1],0)
        for _ in range(9): self.assertIsNone(d.observe(1,1000,self.row(rate=4)))

    def test_training_does_not_accept_attack_or_short_baseline(self):
        d=Detector();d.start()
        for _ in range(20): d.observe(1,1000,self.row(rate=4))
        self.assertEqual(d.samples[1],[])
        for _ in range(4): d.observe(1,1000,self.row())
        with self.assertRaises(ValueError): d.finish()
        self.assertEqual(d.samples[1],[])
        row=self.row();row['transport']=1
        d.observe(1,1000,row)
        self.assertEqual(d.windows[1],[0,0])

class StateTests(unittest.TestCase):
    def setUp(self):
        self.now=0
        self.g=Gateway()
        self.s=State('SIMULATION',clock=lambda:self.now)
        self.advance(2)

    def advance(self,seconds):
        for _ in range(round(seconds/.02)):
            self.now+=.02
            for e in self.g.step(): self.s.accept(e)
            self.s.tick()

    def test_pending_until_ack_even_if_summary_reports_action(self):
        p=self.s.request(2,'quarantine')
        self.assertEqual(self.s.view()['nodes'][1]['state'],'CONTAINMENT PENDING')
        ack=self.g.command(p['wire'])
        # Delaying an ack is modeled by receiving an authoritative summary first.
        self.advance(1)
        self.assertEqual(self.s.view()['nodes'][1]['state'],'CONTAINMENT PENDING')
        # Retry creates a fresh ordered ack; old event sequence is intentionally ignored.
        self.s.accept(self.g.command(p['wire']))
        self.assertEqual(self.s.view()['nodes'][1]['state'],'QUARANTINED')
        self.assertEqual(p['status'],'acknowledged')
        self.assertGreater(self.s.view()['nodes'][1]['quarantine_ms'],13000)

    def test_timeout_and_disconnect_honesty(self):
        p=self.s.request(2,'quarantine')
        with self.assertRaises(ValueError): self.s.request(2,'quarantine')
        self.advance(5.1)
        self.assertEqual(p['status'],'failed')
        self.assertNotEqual(self.s.view()['nodes'][1]['state'],'QUARANTINED')
        self.s.disconnect()
        self.assertEqual(self.s.view()['nodes'][0]['state'],'OFFLINE')
        with self.assertRaises(ValueError): self.s.request(1,'quarantine')
        self.advance(2)
        self.assertTrue(self.s.online())

    def test_known_simulated_attack_is_excluded_from_training(self):
        self.s.detector.start()
        self.s.known_attack = {2}
        self.advance(10)
        self.assertEqual(self.s.detector.samples[2], [])
        self.assertGreater(len(self.s.detector.samples[1]), 0)

    def test_gateway_vs_node_freshness(self):
        self.g.connected[2]=False
        self.advance(4)
        v=self.s.view()
        self.assertTrue(v['gateway_online'])
        self.assertEqual(v['nodes'][0]['state'],'HEALTHY')
        self.assertEqual(v['nodes'][1]['state'],'OFFLINE')

    def test_gateway_restart_does_not_mix_training_sessions(self):
        self.s.detector.start()
        self.advance(12)
        self.assertGreater(len(self.s.detector.samples[1]), 0)
        self.g.session += 1
        self.advance(1.1)
        self.assertTrue(self.s.detector.training)
        self.assertEqual(self.s.detector.samples, {1: [], 2: []})

    def test_frozen_baseline_survives_gateway_restart(self):
        self.s.detector.start()
        self.advance(65)
        baseline = dict(self.s.detector.baselines)
        self.g.session += 1
        self.advance(1.1)
        self.assertEqual(self.s.detector.baselines, baseline)
        self.assertEqual(self.s.detector.streak, {1: 0, 2: 0})

    def test_full_learned_containment_flow(self):
        self.s.detector.start();self.s.gap=True
        self.advance(65)
        self.assertFalse(self.s.detector.training)
        self.s.auto=True
        self.advance(20)
        self.assertFalse(self.s.pending)
        self.g.modes[2]='ANOMALY'
        self.advance(15)
        self.assertIn(2,self.s.pending)
        self.assertNotIn(1,self.s.pending)
        self.assertEqual(self.g.policies[2].until,0)  # 4 Hz never reached gateway's limit
        p=self.s.pending[2]
        self.s.accept(self.g.command(p['wire']))
        self.assertEqual(self.s.view()['nodes'][1]['state'],'QUARANTINED')
        release=self.s.request(2,'release',0)
        self.s.accept(self.g.command(release['wire']))
        self.assertTrue(self.s.auto)
        self.advance(15)
        self.assertIn(2,self.s.pending)  # release never disables future detection

if __name__=='__main__': unittest.main()
