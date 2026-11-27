import unittest
from custom_components.irpat_efficiency.building_report import snapshot, compare


class ReportTests(unittest.TestCase):
    def capture(self, start=0, outside=2, q=48, **kwargs):
        args = dict(room_ids=['a','b'], boundary_id='house', thermal_kwh=q, reviewed=True)
        args.update(kwargs)
        return snapshot({str(t):22 for t in range(start,start+86401,300)},
                        {str(t):outside for t in range(start,start+86401,300)},
                        start,start+86400,**args)

    def test_normalization(self):
        a=self.capture()
        b=self.capture(86400,12,24)
        self.assertEqual(a['degree_hours'],480)
        self.assertEqual(a['apparent_w_per_k'],100)
        self.assertAlmostEqual(compare(a,b,intervention_at=86400,comparable=True)['normalized_change_pct'],0)

    def test_observed_change(self):
        r=compare(self.capture(),self.capture(86400,q=36),intervention_at=86400,comparable=True)
        self.assertAlmostEqual(r['normalized_change_pct'],-25)
        self.assertFalse(r['causal_savings_confirmed'])

    def test_missing_data(self):
        with self.assertRaises(ValueError):
            snapshot({}, {},0,86400,room_ids=['a'],boundary_id='house',thermal_kwh=48,reviewed=True)

    def test_nonheating(self):
        with self.assertRaises(ValueError): self.capture(outside=23)

    def test_review(self):
        with self.assertRaises(ValueError): self.capture(reviewed=False)
        with self.assertRaises(ValueError): compare(self.capture(),self.capture(86400),intervention_at=86400)

    def test_incompatible(self):
        for opts in ({'boundary_id':'different'},{'room_ids':['a']}):
            with self.assertRaises(ValueError):
                compare(self.capture(),self.capture(86400,**opts),intervention_at=86400,comparable=True)

    def test_invalid_intervention(self):
        with self.assertRaises(ValueError): compare(self.capture(),self.capture(86400),intervention_at=100,comparable=True)

    def test_invalid_energy(self):
        for q in (0,None,float('nan'),True):
            with self.assertRaises(ValueError): self.capture(q=q)

    def test_duplicate_rooms(self):
        with self.assertRaises(ValueError): self.capture(room_ids=['a','a'])
