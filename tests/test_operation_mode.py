import unittest
from custom_components.irpat_efficiency.operation_mode import configure_mode, classify_mode


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.t = {'sources': [{'id': 's'}]}
        self.config = configure_mode(self.t, 's', 'sensor.mode', heating='1', cooling='2',
                                     dhw='3', standby='0', defrost='4', off='5')
        self.binding = self.config['sources'][0]['mode_binding']

    def test_all_states(self):
        for raw, expected in [('1','heating'),('2','cooling'),('3','dhw'),('0','standby'),('4','defrost'),('5','off')]:
            result = classify_mode(self.binding, raw, 1000, 1000)
            self.assertEqual(result['mode'], expected)
            self.assertFalse(result['interval_confirmed'])

    def test_optional(self):
        self.assertEqual(classify_mode(None, '1', 1000, 1000)['status'], 'not_configured')
        self.assertNotIn('mode_binding', self.t['sources'][0])
        self.assertNotIn('mode_binding', configure_mode(self.config, 's')['sources'][0])

    def test_unknown(self):
        for raw in (None, 'unknown', 'unavailable'):
            self.assertEqual(classify_mode(self.binding, raw, 1000, 1000)['status'], 'unavailable')
        self.assertEqual(classify_mode(self.binding, '6', 1000, 1000)['status'], 'unmapped')

    def test_stale(self):
        for timestamp in (None, 699, 1001, float('nan')):
            self.assertEqual(classify_mode(self.binding, '1', timestamp, 1000)['status'], 'stale')

    def test_duplicate_and_reserved(self):
        for fields in ({'heating':'1','dhw':'1'}, {'heating':'unknown'}, {'heating':' '}, {}):
            with self.assertRaises(ValueError):
                configure_mode(self.t, 's', 'sensor.mode', **fields)

    def test_bad_source_or_domain(self):
        with self.assertRaises(ValueError):
            configure_mode(self.t, 'missing', 'sensor.mode', heating='1')
        with self.assertRaises(ValueError):
            configure_mode(self.t, 's', 'climate.mode', heating='1')

    def test_exact_match(self):
        binding = configure_mode(self.t, 's', 'sensor.mode', heating='Heat')['sources'][0]['mode_binding']
        self.assertEqual(classify_mode(binding, 'heat', 1000, 1000)['status'], 'unmapped')
