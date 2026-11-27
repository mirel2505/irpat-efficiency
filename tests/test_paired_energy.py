import unittest
from custom_components.irpat_efficiency.mode_history import observation
from custom_components.irpat_efficiency.paired_energy import matched_heat


class PairedTests(unittest.TestCase):
    def sample(self, t, power=4000, raw='h', changed=0, confirmed=True):
        binding = {'entity_id':'sensor.mode','mapping':{'h':'heating','c':'cooling','d':'dhw','f':'defrost'}}
        mode = observation(binding, raw, changed, t, t)
        return {'timestamp':t, 'pair':{'confirmed':confirmed, 'mode':mode,
                 'thermal':{'entity_id':'sensor.heat','status':'reported','timestamp':t,'value':power}}}

    def test_heating(self):
        mode, q = matched_heat(self.sample(0), self.sample(300))
        self.assertEqual(mode,'heating')
        self.assertAlmostEqual(q, 1/3)

    def test_cooling_signed(self):
        mode, q = matched_heat(self.sample(0,-3000,'c'), self.sample(300,-3000,'c'))
        self.assertEqual(mode,'cooling')
        self.assertAlmostEqual(q,-.25)

    def test_negative_heat_retained(self):
        self.assertEqual(matched_heat(self.sample(0,-1200),self.sample(300,-1200)),('heating',-.1))

    def test_excludes_other_modes_and_transitions(self):
        for mode in ('d','f'):
            self.assertEqual(matched_heat(self.sample(0,raw=mode),self.sample(300,raw=mode)),(None,None))
        self.assertEqual(matched_heat(self.sample(0),self.sample(300,changed=100)),(None,None))

    def test_unconfirmed_and_missing(self):
        self.assertEqual(matched_heat(self.sample(0),self.sample(300,confirmed=False)),(None,None))
        self.assertEqual(matched_heat({},self.sample(300)),(None,None))

    def test_skew_and_replacement(self):
        a,b = self.sample(0),self.sample(300)
        b['pair']['thermal']['timestamp']=290
        self.assertEqual(matched_heat(a,b),(None,None))
        b=self.sample(300)
        b['pair']['thermal']['entity_id']='sensor.other'
        self.assertEqual(matched_heat(a,b),(None,None))

    def test_gap_and_invalid(self):
        self.assertEqual(matched_heat(self.sample(0),self.sample(600)),(None,None))
        self.assertEqual(matched_heat(self.sample(0),self.sample(300,float('nan'))),(None,None))
