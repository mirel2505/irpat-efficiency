import asyncio
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from custom_components.irpat_efficiency.backup import async_pre_backup, async_post_backup
from custom_components.irpat_efficiency.const import DOMAIN
from custom_components.irpat_efficiency.event_journal import EventJournal


class Disk:
    def __init__(self, fail=False):
        self.data = None
        self.fail = fail
        self.writes = 0

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        if self.fail:
            raise OSError('disk failure')
        self.data = deepcopy(data)
        self.writes += 1


class BackupTests(unittest.IsolatedAsyncioTestCase):
    def monitor(self, key='end', fail=False, closed=False):
        disk = Disk(fail)
        journal = EventJournal(disk, key, 2000)
        event = {'source_id': 'hp', key: datetime.now(timezone.utc).timestamp()}
        journal.append(event)
        return NS(journal=journal, lock=asyncio.Lock(), closed=closed), disk, event

    async def test_flush_both_journals(self):
        a, da, ea = self.monitor()
        b, db, eb = self.monitor('observed_at')
        hass = NS(data={DOMAIN: {'defrost_monitors': {'e': a}, 'mode_monitors': {'e': b}}})
        await async_pre_backup(hass)
        await async_post_backup(hass)
        self.assertEqual(da.data['events'], [ea])
        self.assertEqual(db.data['events'], [eb])
        self.assertFalse(a.journal.pending)
        self.assertFalse(b.journal.pending)
        await async_pre_backup(hass)
        self.assertEqual((da.writes, db.writes), (1, 1))

    async def test_failure_preserves_pending_and_other_journal(self):
        a, da, ea = self.monitor(fail=True)
        b, db, eb = self.monitor('observed_at')
        hass = NS(data={DOMAIN: {'defrost_monitors': {'e': a}, 'mode_monitors': {'e': b}}})
        with self.assertLogs(level='ERROR'):
            await async_pre_backup(hass)
        self.assertEqual(a.journal.pending, [ea])
        self.assertTrue(a.journal.save_failed)
        self.assertEqual(db.data['events'], [eb])
        da.fail = False
        await async_pre_backup(hass)
        self.assertEqual(da.data['events'], [ea])

    async def test_closed_monitor_not_written(self):
        a, da, _ = self.monitor(closed=True)
        await async_pre_backup(NS(data={DOMAIN: {'defrost_monitors': {'e': a}}}))
        self.assertEqual(da.writes, 0)

    async def test_warns_on_uncommitted_history(self):
        hass = NS(data={DOMAIN: {'histories': {'e': NS(save_failed=True)},
                                 'energy_monitors': {'e': NS(save_failed=True)}}})
        with self.assertLogs(level='WARNING') as logs:
            await async_pre_backup(hass)
        self.assertEqual(len(logs.output), 2)

    async def test_missing_runtime(self):
        hass = NS(data={})
        await async_pre_backup(hass)
        await async_post_backup(hass)
        self.assertEqual(hass.data, {})
