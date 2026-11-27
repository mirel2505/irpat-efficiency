import unittest
from copy import deepcopy
from datetime import timezone
from custom_components.irpat_efficiency.energy_store import EnergyStore


class FakeStore:
    data = None
    fail = False

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        if self.fail:
            raise OSError('disk error')
        self.data = deepcopy(data)


class EnergyStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.disk = FakeStore()
        self.store = EnergyStore(self.disk)
        await self.store.async_load()

    def sample(self, t, v, entity='sensor.meter', status='reported', age=0):
        return {'s': {'entity_id': entity, 'value': v, 'timestamp': t-age, 'status': status}}

    async def add(self, t, v, **kw):
        await self.store.async_sample(self.sample(t, v, **kw), t, timezone.utc)

    def total(self, t, entity='sensor.meter'):
        return self.store.overview(self.sample(t, 0, entity), t, timezone.utc)['s']['daily']['electric_kwh']

    async def test_persistence_and_restart(self):
        await self.add(0, 10)
        await self.add(300, 11)
        self.assertEqual(self.total(300), 1)
        self.store = EnergyStore(self.disk)
        await self.store.async_load()
        await self.add(600, 12)
        self.assertEqual(self.total(600), 1)
        await self.add(900, 13)
        self.assertEqual(self.total(900), 2)

    async def test_gap(self):
        await self.add(0, 10)
        await self.add(600, 12)
        self.assertIsNone(self.total(600))

    async def test_stale(self):
        await self.add(0, 10)
        await self.add(300, 11, age=90)
        await self.add(600, 12)
        self.assertIsNone(self.total(600))

    async def test_reset(self):
        await self.add(0, 10)
        await self.add(300, 1)
        await self.add(600, 2)
        self.assertEqual(self.total(600), 1)

    async def test_replacement(self):
        await self.add(0, 10)
        await self.add(300, 11)
        await self.add(600, 50, entity='sensor.other')
        await self.add(900, 52, entity='sensor.other')
        self.assertEqual(self.total(900, 'sensor.other'), 2)
        self.assertEqual(len(self.store.data['s']), 2)

    async def test_failed_save(self):
        await self.add(0, 10)
        self.disk.fail = True
        with self.assertRaises(OSError):
            await self.add(300, 11)
        self.assertIsNone(self.total(300))
        self.disk.fail = False
        await self.add(600, 12)
        self.assertIsNone(self.total(600))

    async def test_zero(self):
        await self.add(0, 10)
        await self.add(300, 10)
        self.assertEqual(self.total(300), 0)
