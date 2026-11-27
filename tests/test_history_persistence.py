import unittest
from copy import deepcopy
from datetime import timezone

from custom_components.irpat_efficiency.history import compare_room
from custom_components.irpat_efficiency.history_persistence import save_sample, current_series


class Disk:
    def __init__(self):
        self.data = None
        self.fail = False

    async def async_save(self, data):
        if self.fail:
            raise OSError('disk failure')
        self.data = deepcopy(data)


class HistoryPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_save_leaves_committed_history_unchanged(self):
        disk = Disk()
        old = await save_sample(disk, {}, None, None, 'a', 0, {'r': 20})
        disk.fail = True
        with self.assertRaises(OSError):
            await save_sample(disk, old['rooms'], 'a', 0, 'b', 300, {'r': 24})
        self.assertEqual(old, disk.data)
        self.assertEqual(old['rooms'], {'r': {'0': 20}})
        self.assertEqual(current_series(old['rooms'], 'a', 0, 'b'), {})

    async def test_success_after_failure_and_restart(self):
        disk = Disk()
        old = await save_sample(disk, {}, None, None, 'a', 0, {'r': 20})
        disk.fail = True
        with self.assertRaises(OSError):
            await save_sample(disk, old['rooms'], 'a', 0, 'a', 300, {'r': 21})
        disk.fail = False
        new = await save_sample(disk, old['rooms'], 'a', 0, 'a', 600, {'r': 22})
        self.assertEqual(new, disk.data)
        reloaded = deepcopy(disk.data)
        series = current_series(reloaded['rooms'], reloaded['configuration_hash'],
                                reloaded['configuration_since'], 'a')
        self.assertEqual(series['r'], {'0': 20, '600': 22})
        self.assertEqual(compare_room(series['r'], 900, timezone.utc)['windows']['24']['count'], 2)

    async def test_configuration_change_excludes_transition_slot(self):
        disk = Disk()
        old = await save_sample(disk, {}, None, None, 'a', 0, {'r': 20})
        new = await save_sample(disk, old['rooms'], 'a', 0, 'b', 301, {'r': 24})
        latest = await save_sample(disk, new['rooms'], 'b', new['configuration_since'], 'b', 600, {'r': 25})
        self.assertEqual(latest['configuration_since'], 301)
        self.assertEqual(current_series(latest['rooms'], 'b', 301, 'b'), {'r': {'600': 25}})
        self.assertIn('0', latest['rooms']['r'])

    async def test_legacy_missing_epoch(self):
        disk = Disk()
        self.assertEqual(current_series({'r': {'0': 20}}, 'a', None, 'a'), {})
        new = await save_sample(disk, {'r': {'0': 20}}, 'a', None, 'a', 300, {'r': 22})
        self.assertEqual(current_series(new['rooms'], 'a', 300, 'a'), {'r': {'300': 22}})

    async def test_invalid_timestamp(self):
        disk = Disk()
        with self.assertRaises(ValueError):
            await save_sample(disk, {}, None, None, 'a', float('nan'), {})
        self.assertIsNone(disk.data)

    async def test_snapshot_isolation(self):
        disk = Disk()
        saved = await save_sample(disk, {}, None, None, 'a', 0, {'r': 20})
        saved['rooms']['r']['0'] = 100
        self.assertEqual(disk.data['rooms']['r']['0'], 20)
