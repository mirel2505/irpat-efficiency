import unittest
from custom_components.irpat_efficiency.defrost import enabled_sources, observe


class DefrostTests(unittest.TestCase):
    def step(self, old, t, active, energy=None, supply=None, **kwargs):
        return observe(old, dict(timestamp=t, active=active, electric_kwh=energy,
                                 supply_c=supply), **kwargs)

    def sequence(self, samples, confirmed=True):
        state = None
        events = []
        for t, active, energy, supply in samples:
            state, event = self.step(state, t, active, energy, supply, boundary_confirmed=confirmed)
            if event:
                events.append(event)
        return events

    def test_optional_sources(self):
        topology = {'sources': [{'id':'a','source_type':'heat_pump'}, {'id':'b','source_type':'gas'},
                                {'id':'c','source_type':'heat_pump'}, {'id':'d','source_type':'hybrid'}],
                    'telemetry': [{'group':'sources','owner_id':i,'role':'defrost'} for i in ('a','b','d')]}
        self.assertEqual(enabled_sources(topology), {'a','d'})
        self.assertEqual(enabled_sources({'sources':topology['sources']}), set())

    def test_complete(self):
        events = self.sequence([(0,False,10,34),(30,True,10.01,33),(60,True,10.03,28),(90,False,10.05,29)])
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['duration_s'],60)
        self.assertAlmostEqual(events[0]['electric_kwh'],.04)
        self.assertEqual(events[0]['observed_supply_drop_c'],5)

    def test_start_already_active(self):
        self.assertEqual(self.sequence([(0,True,10,34),(30,False,11,33)]),[])

    def test_gap(self):
        self.assertEqual(self.sequence([(0,False,10,34),(30,True,11,33),(180,False,12,29)]),[])

    def test_unknown(self):
        self.assertEqual(self.sequence([(0,False,10,34),(30,True,11,33),(60,None,12,29),(90,False,13,30)]),[])

    def test_reset(self):
        event = self.sequence([(0,False,9,34),(30,True,10,33),(60,True,1,28),(90,False,11,29)])[0]
        self.assertIsNone(event['electric_kwh'])
        self.assertEqual(event['duration_s'],60)

    def test_missing_energy(self):
        event = self.sequence([(0,False,9,34),(30,True,10,33),(60,True,None,28),(90,False,11,29)])[0]
        self.assertIsNone(event['electric_kwh'])

    def test_unconfirmed_boundary(self):
        event = self.sequence([(0,False,9,34),(30,True,10,33),(60,False,11,28)],False)[0]
        self.assertIsNone(event['electric_kwh'])

    def test_missing_supply(self):
        event = self.sequence([(0,False,None,None),(30,True,None,None),(60,False,None,None)])[0]
        self.assertIsNone(event['observed_supply_drop_c'])

    def test_repeated_off(self):
        self.assertEqual(self.sequence([(0,False,10,34),(30,False,11,33)]),[])
