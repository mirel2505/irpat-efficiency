import unittest
from custom_components.irpat_efficiency.comparison import heating_observation, compare


class ComparisonTests(unittest.TestCase):
    def period(self, start=0, heat=48, air=22, outside=2, **kwargs):
        end = start+86400
        indoor = {str(s):air for s in range(start,end+300,300)}
        outdoor = {str(s):outside for s in range(start,end+300,300)}
        return heating_observation(indoor,outdoor,start,end,heat,**{
            'scope_id':'zone','measurement_id':'net_heat','full_heat_coverage':True,**kwargs})

    def test_degree_hours(self):
        r = self.period()
        self.assertEqual(r['degree_hours'],480)
        self.assertEqual(r['apparent_w_per_k'],100)
        self.assertEqual(r['indoor_mean_c'],22)

    def test_weather_normalized(self):
        a,b = self.period(),self.period(172800,heat=28.8,outside=7)
        r = compare(a,b,86400,reviewed=True)
        self.assertAlmostEqual(r['apparent_reduction_pct'],20)
        self.assertFalse(r['causal_savings'])

    def test_no_false_improvement_from_weather(self):
        a,b = self.period(),self.period(172800,heat=36,outside=7)
        self.assertAlmostEqual(compare(a,b,86400,reviewed=True)['apparent_change_pct'],0)

    def test_worse(self):
        r = compare(self.period(),self.period(172800,heat=60),86400,reviewed=True)
        self.assertEqual(r['apparent_change_pct'],25)

    def test_requires_review(self):
        self.assertEqual(compare(self.period(),self.period(172800),86400)['status'],'review_required')

    def test_incomplete_heat(self):
        r = self.period(full_heat_coverage=False)
        self.assertIsNone(r['apparent_w_per_k'])
        self.assertEqual(compare(r,self.period(172800),86400,reviewed=True)['status'],'insufficient_data')

    def test_missing_endpoint(self):
        r = heating_observation({'0':22},{'0':2},0,86400,48,scope_id='zone',
                                measurement_id='net_heat',full_heat_coverage=True)
        self.assertLess(r['coverage'],1)
        self.assertIsNone(r['apparent_w_per_k'])

    def test_mismatched_boundary(self):
        a = self.period()
        for b in (self.period(172800,scope_id='other'),self.period(172800,measurement_id='other')):
            self.assertEqual(compare(a,b,86400,reviewed=True)['status'],'not_comparable')

    def test_comfort_and_intervention(self):
        a = self.period()
        self.assertEqual(compare(a,self.period(172800,air=21),86400,reviewed=True)['status'],'not_comparable')
        self.assertEqual(compare(a,self.period(172800),200000,reviewed=True)['status'],'not_comparable')

    def test_invalid_values(self):
        for r in (self.period(heat=0),self.period(heat=float('nan')),self.period(outside=23)):
            self.assertIsNone(r['apparent_w_per_k'])
