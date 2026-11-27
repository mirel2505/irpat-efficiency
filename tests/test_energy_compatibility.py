import unittest
from datetime import timezone
from copy import deepcopy
from custom_components.irpat_efficiency.energy_store import EnergyStore
from custom_components.irpat_efficiency.mode_history import observation


class Disk:
    data = None
    async def async_load(self):
        return deepcopy(self.data)
    async def async_save(self, data):
        self.data = deepcopy(data)


class EnergyCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.disk = Disk()
        self.store = EnergyStore(self.disk)
        await self.store.async_load()

    def sample(self, t, value, thermal='sensor.heat', power=3600, mode='h', changed=0, confirmed=True):
        binding = {'entity_id': 'sensor.mode', 'mapping': {'h': 'heating', 'd': 'dhw'}}
        return {'entity_id': 'sensor.electric', 'value': value, 'timestamp': t, 'status': 'reported',
                'pair_signature': [thermal, 'sensor.mode'] if confirmed else None,
                'pair': {'confirmed': confirmed, 'mode': observation(binding, mode, changed, t, t),
                         'thermal': {'entity_id': thermal, 'timestamp': t, 'value': power, 'status': 'reported'}}}

    async def add(self, t, value, **kwargs):
        await self.store.async_sample({'s': self.sample(t, value, **kwargs)}, t, timezone.utc)

    def result(self, t, **kwargs):
        return self.store.overview({'s': self.sample(t, 0, **kwargs)}, t, timezone.utc)['s']['daily']

    async def test_thermal_replacement_does_not_mix_ratios(self):
        await self.add(0, 10)
        await self.add(300, 10.1)
        self.assertAlmostEqual(self.result(300)['modes']['heating']['cop'], 3)
        await self.add(600, 10.2, thermal='sensor.new', power=7200)
        await self.add(900, 10.3, thermal='sensor.new', power=7200)
        row = self.result(900, thermal='sensor.new')
        self.assertAlmostEqual(row['electric_kwh'], .3)
        self.assertAlmostEqual(row['modes']['heating']['cop'], 6)
        self.assertEqual(row['modes']['heating']['seconds'], 300)

    async def test_revoked_confirmation_hides_old_ratio(self):
        await self.add(0, 10)
        await self.add(300, 10.1)
        self.assertIsNone(self.result(300, confirmed=False)['modes']['heating']['cop'])

    async def test_mode_change_keeps_electricity(self):
        await self.add(0, 10)
        await self.add(300, 10.1)
        await self.add(600, 10.3, mode='d', changed=400)
        row = self.result(600)
        self.assertAlmostEqual(row['electric_kwh'], .3)
        self.assertEqual(row['modes']['heating']['seconds'], 300)

    async def test_pair_identity_survives_restart(self):
        await self.add(0, 10)
        await self.add(300, 10.1)
        self.store = EnergyStore(self.disk)
        await self.store.async_load()
        await self.add(600, 10.2)
        await self.add(900, 10.3)
        self.assertEqual(self.result(900)['modes']['heating']['seconds'], 600)

    async def test_duplicate_meter_not_attributed(self):
        for t,v in [(0,10),(300,11)]:
            await self.store.async_sample({'a': self.sample(t,v), 'b': self.sample(t,v)}, t, timezone.utc)
        rows = self.store.overview({'a': self.sample(300,11), 'b': self.sample(300,11)},300,timezone.utc)
        for row in rows.values():
            self.assertIsNone(row['daily']['electric_kwh'])
            self.assertEqual(row['daily']['status'], 'shared_meter')

    def test_signature_from_configuration(self):
        from custom_components.irpat_efficiency.paired_energy import pair_signature
        source = {'id':'s', 'source_type':'heat_pump', 'power_boundary_confirmed':True,
                  'energy_boundary_confirmed':True, 'mode_binding':{'entity_id':'sensor.mode','mapping':{'h':'heating'}}}
        t = {'sources':[source], 'telemetry':[
            {'group':'sources','owner_id':'s','role':r,'entity_id':'sensor.'+r}
            for r in ('electrical_energy','electrical_power','thermal_power')]}
        signature = pair_signature(t,'s')
        self.assertIsNotNone(signature)
        self.assertEqual(signature, deepcopy(signature))
        other = deepcopy(t)
        other['telemetry'][-1]['entity_id'] = 'sensor.new'
        self.assertNotEqual(signature, pair_signature(other,'s'))
        other['telemetry'].append(dict(other['telemetry'][-1], owner_id='other'))
        self.assertIsNone(pair_signature(other,'s'))
        source['energy_boundary_confirmed'] = False
        self.assertIsNone(pair_signature(t,'s'))
