import unittest
from custom_components.irpat_efficiency.efficiency import (
    energy_summary, counter_delta, apparent_loss_w_per_k, fuel_efficiency,
)


class EfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.q = {str(s): 4000 for s in range(0,3601,300)}
        self.e = {str(s): 1000 for s in range(0,3601,300)}

    def summary(self, **kwargs):
        return energy_summary(self.q,self.e,0,3600,**{
            'mode':'heating','boundary_confirmed':True,**kwargs})

    def test_complete(self):
        r = self.summary(tariff=1.2,area_m2=100)
        self.assertEqual(r['status'],'complete')
        self.assertAlmostEqual(r['thermal_kwh'],4)
        self.assertAlmostEqual(r['electrical_kwh'],1)
        self.assertAlmostEqual(r['cop'],4)
        self.assertAlmostEqual(r['cost'],1.2)
        self.assertAlmostEqual(r['thermal_kwh_m2'],.04)

    def test_missing_interval(self):
        del self.e['300']
        r = self.summary()
        self.assertEqual(r['status'],'partial')
        self.assertAlmostEqual(r['coverage'],10/12)
        self.assertAlmostEqual(r['thermal_kwh'],4*10/12)
        self.assertAlmostEqual(r['cop'],4)

    def test_no_data_or_boundary(self):
        self.assertEqual(self.summary(boundary_confirmed=False)['status'],'review_required')
        self.e.clear()
        self.assertIsNone(self.summary()['cop'])

    def test_defrost_net(self):
        self.q['300'] = -2000
        self.assertAlmostEqual(self.summary()['thermal_kwh'],3.5)

    def test_cooling(self):
        self.q = {k:-v for k,v in self.q.items()}
        self.assertAlmostEqual(self.summary(mode='cooling')['cop'],4)

    def test_zero_electric(self):
        self.e = {k:0 for k in self.e}
        self.assertIsNone(self.summary()['cop'])

    def test_invalid_samples(self):
        self.e['300'] = -1
        self.q['900'] = float('nan')
        self.assertAlmostEqual(self.summary()['coverage'],8/12)

    def test_counter(self):
        self.assertEqual(counter_delta(20,22),2)
        self.assertIsNone(counter_delta(22,1))
        self.assertIsNone(counter_delta(None,1))

    def test_apparent_loss(self):
        self.assertEqual(apparent_loss_w_per_k(48,480,reviewed=True,coverage=1),100)
        self.assertIsNone(apparent_loss_w_per_k(48,480,reviewed=True,coverage=.9))
        self.assertIsNone(apparent_loss_w_per_k(48,0,reviewed=True,coverage=1))

    def test_fuel(self):
        self.assertAlmostEqual(fuel_efficiency(9,10,basis='HHV',boundary_confirmed=True),.9)
        self.assertIsNone(fuel_efficiency(9,10,basis='unknown',boundary_confirmed=True))
        self.assertIsNone(fuel_efficiency(9,0,basis='LHV',boundary_confirmed=True))

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            energy_summary(self.q,self.e,0,301,mode='heating')
