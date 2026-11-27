import unittest
from custom_components.irpat_efficiency.telemetry import convert, set_binding


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.t = {'rooms': [{'id': 'r'}], 'sources': [{'id': 's'}], 'manifolds': [{'id': 'm'}]}

    def test_add_replace_remove(self):
        a = set_binding(self.t, 'rooms', 'r', 'humidity', 'sensor.a', 'Humidity')
        b = set_binding(a, 'rooms', 'r', 'humidity', 'sensor.b')
        self.assertEqual(b['telemetry'][0]['entity_id'], 'sensor.b')
        self.assertEqual(a['telemetry'][0]['entity_id'], 'sensor.a')
        self.assertNotIn('telemetry', self.t)
        self.assertEqual(set_binding(b, 'rooms', 'r', 'humidity', None)['telemetry'], [])

    def test_wrong_owner_role(self):
        with self.assertRaises(ValueError):
            set_binding(self.t, 'rooms', 'r', 'flow', 'sensor.a')
        with self.assertRaises(ValueError):
            set_binding(self.t, 'rooms', 'unknown', 'humidity', 'sensor.a')

    def test_wrong_domain(self):
        with self.assertRaises(ValueError):
            set_binding(self.t, 'sources', 's', 'defrost', 'sensor.a')
        with self.assertRaises(ValueError):
            set_binding(self.t, 'sources', 's', 'flow', 'switch.a')

    def test_flow(self):
        self.assertEqual(convert('flow', 20, 'L/min'), (1.2, 'm³/h'))
        self.assertEqual(convert('flow', 1200, 'L/h'), (1.2, 'm³/h'))
        self.assertEqual(convert('flow', 0, 'm³/h'), (0, 'm³/h'))

    def test_power_and_energy(self):
        self.assertEqual(convert('thermal_power', -2, 'kW'), (-2000, 'W'))
        self.assertEqual(convert('electrical_power', -2, 'kW'), (None, 'W'))
        self.assertEqual(convert('electrical_energy', 1200, 'Wh'), (1.2, 'kWh'))

    def test_pressure_and_temperature(self):
        self.assertEqual(convert('pressure', 100, 'kPa'), (1, 'bar'))
        self.assertEqual(convert('supply_temperature', 86, '°F'), (30, '°C'))

    def test_invalid(self):
        for v in (None, True, 'unknown', 'nan', -1, 101):
            self.assertEqual(convert('humidity', v, '%'), (None, '%'))
        self.assertEqual(convert('flow', 1, 'unknown'), (None, 'm³/h'))

    def test_binary(self):
        self.assertEqual(convert('defrost', 'on', None), (True, None))
        self.assertEqual(convert('defrost', 'off', None), (False, None))
        self.assertEqual(convert('defrost', 'unknown', None), (None, None))
