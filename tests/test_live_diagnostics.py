import unittest
from custom_components.irpat_efficiency.live_diagnostics import source_metrics, live_diagnostics


def sample(value, stamp=1000):
    return {'value':value,'timestamp':stamp,'status':'reported'}


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.source = {'source_type':'heat_pump'}
        self.samples = {k:sample(v) for k,v in [('supply_temperature',35),('return_temperature',30),
                        ('flow',1),('thermal_power',4000),('electrical_power',1000)]}

    def test_no_fluid_assumption(self):
        r = source_metrics(self.source,self.samples,1000)
        self.assertEqual(r['delta_t_c'],5)
        self.assertIsNone(r['thermal_calculated_w'])
        self.assertIsNone(r['signed_power_ratio'])

    def test_fluid_supplied(self):
        self.source.update(density_kg_m3=1000,cp_j_kgk=4180)
        self.assertAlmostEqual(source_metrics(self.source,self.samples,1000)['thermal_calculated_w'],5805.5555556)

    def test_boundary_and_signed_ratio(self):
        self.source['power_boundary_confirmed'] = True
        self.samples['thermal_power'] = sample(-2000)
        self.assertEqual(source_metrics(self.source,self.samples,1000)['signed_power_ratio'],-2)

    def test_stale_or_skewed(self):
        self.source['power_boundary_confirmed'] = True
        self.samples['thermal_power'] = sample(4000,600)
        self.assertIsNone(source_metrics(self.source,self.samples,1000)['signed_power_ratio'])
        self.samples['electrical_power'] = sample(1000,0)
        self.assertIsNone(source_metrics(self.source,self.samples,1000)['electrical_w'])

    def test_gas(self):
        self.source.update(source_type='gas',power_boundary_confirmed=True)
        self.assertEqual(source_metrics(self.source,self.samples,1000)['cop_status'],'not_heat_pump')

    def test_room(self):
        topology = {'sources':[],'rooms':[{'id':'r'}],'circuits':[{'room_id':'r','manifold_id':'m'}]}
        telemetry = [{**sample(60),'group':'rooms','owner_id':'r','role':'humidity'},
                     {**sample(16),'group':'manifolds','owner_id':'m','role':'supply_temperature'}]
        readings = [{'temperature_c':25,'reported_at':'1970-01-01T00:16:40+00:00'}]
        rooms = {'r':{'readings':readings}}
        result = live_diagnostics(topology,telemetry,rooms,1000)
        self.assertEqual(result['condensation']['r']['status'],'review_risk')
        readings.append(dict(readings[0]))
        self.assertEqual(live_diagnostics(topology,telemetry,rooms,1000)['condensation']['r']['status'],'unknown')
