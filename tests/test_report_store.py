import unittest
from copy import deepcopy
from custom_components.irpat_efficiency.report_store import ReportStore


class FakeStore:
    def __init__(self):
        self.data = None
        self.fail = False

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        if self.fail:
            raise OSError('disk error')
        self.data = deepcopy(data)


class ReportStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.disk = FakeStore()
        self.store = ReportStore(self.disk)
        await self.store.async_load()

    async def capture(self, start=0, q=48, signature='same', **kwargs):
        args = dict(room_ids=['a', 'b'], boundary_id='house', thermal_kwh=q, reviewed=True)
        args.update(kwargs)
        return await self.store.async_capture('Observation',
            {str(t): 22 for t in range(start, start+86401, 300)},
            {str(t): 2 for t in range(start, start+86401, 300)},
            start, start+86400, measurement_signature=signature, **args)

    async def test_persistence_and_compare(self):
        a = await self.capture()
        self.store = ReportStore(self.disk)
        await self.store.async_load()
        b = await self.capture(86400, 36)
        result = await self.store.async_compare(a['id'], b['id'], name='Insulation',
                                                intervention_at=86400, comparable=True)
        self.assertAlmostEqual(result['normalized_change_pct'], -25)
        self.assertFalse(result['causal_savings_confirmed'])
        self.store = ReportStore(self.disk)
        await self.store.async_load()
        self.assertEqual(len(self.store.overview()['reports']), 1)

    async def test_measurement_change(self):
        a = await self.capture()
        b = await self.capture(86400, signature='different')
        with self.assertRaisesRegex(ValueError, 'incompatible_measurements'):
            await self.store.async_compare(a['id'], b['id'], name='Comparison', intervention_at=86400, comparable=True)

    async def test_review_required(self):
        with self.assertRaises(ValueError):
            await self.capture(reviewed=False)
        a = await self.capture()
        b = await self.capture(86400)
        with self.assertRaisesRegex(ValueError, 'review_required'):
            await self.store.async_compare(a['id'], b['id'], name='Comparison', intervention_at=86400)

    async def test_failed_save(self):
        a = await self.capture()
        b = await self.capture(86400)
        self.disk.fail = True
        with self.assertRaises(OSError):
            await self.capture(172800)
        with self.assertRaises(OSError):
            await self.store.async_compare(a['id'], b['id'], name='Comparison', intervention_at=86400, comparable=True)
        self.assertEqual(len(self.store.overview()['observations']), 2)
        self.assertEqual(self.store.overview()['reports'], [])

    async def test_snapshot_isolation(self):
        a = await self.capture()
        a['thermal_kwh'] = 1
        view = self.store.overview()
        view['observations'][0]['thermal_kwh'] = 2
        self.assertEqual(self.store.overview()['observations'][0]['thermal_kwh'], 48)

    async def test_invalid_reference(self):
        a = await self.capture()
        for key in ('missing', a['id']):
            with self.assertRaisesRegex(ValueError, 'invalid_reference'):
                await self.store.async_compare(a['id'], key, name='Comparison', intervention_at=86400, comparable=True)

    async def test_closed(self):
        await self.store.async_close()
        with self.assertRaisesRegex(ValueError, 'store_closed'):
            await self.capture()
