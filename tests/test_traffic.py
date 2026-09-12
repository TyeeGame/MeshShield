import unittest
from backend.traffic import Traffic
from backend.protocol import validate

class TrafficTests(unittest.TestCase):
    def test_modes_fairness_and_actual_packets(self):
        source=Traffic()
        source.set_mode('FLOOD')
        counts={1:0,2:0}
        for tick in range(1000):
            for line in source.due(tick/100,77):
                prefix,session,node,data=line.decode().strip().split(',')
                self.assertEqual((prefix,session),('T','77'))
                self.assertEqual(validate(bytes.fromhex(data)),'allowed')
                counts[int(node)]+=1
        self.assertEqual(counts[1],10)
        self.assertGreater(counts[2],150)

    def test_no_catchup_burst_and_new_session(self):
        source=Traffic()
        source.due(0,10)
        self.assertLessEqual(len(source.due(500,10)),2)
        self.assertEqual(source.due(500,10),[])
        self.assertTrue(all(b'T,11,' in line for line in source.due(501,11)))

    def test_unknown_and_recovery(self):
        source=Traffic()
        source.due(0,10)
        source.set_mode('UNKNOWN_TYPE')
        line=source.due(.3,10)[0]
        self.assertEqual(validate(bytes.fromhex(line.decode().strip().split(',')[3])),'unknown_type')
        source.set_mode('NORMAL')
        line=source.due(.31,10)[0]
        self.assertEqual(validate(bytes.fromhex(line.decode().strip().split(',')[3])),'allowed')
        with self.assertRaises(ValueError):source.set_mode('bad')
