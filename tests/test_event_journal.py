import unittest
from copy import deepcopy
from custom_components.irpat_efficiency.event_journal import EventJournal


class Disk:
    def __init__(self):
        self.data = None
        self.fail = False
    async def async_load(self):
        return deepcopy(self.data)
    async def async_save(self, data):
        if self.fail:
            raise OSError('disk failure')
        self.data = deepcopy(data)


class EventJournalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.disk = Disk()
        self.journal = EventJournal(self.disk, 'end', 3, 1000)
        await self.journal.async_load()

    def event(self, stamp, source='hp'):
        return {'source_id': source, 'end': stamp}

    async def test_failure_and_retry(self):
        self.journal.append(self.event(10))
        await self.journal.async_flush(10)
        self.disk.fail = True
        self.journal.append(self.event(20))
        with self.assertRaises(OSError):
            await self.journal.async_flush(20)
        self.assertEqual(self.journal.overview('hp'), {'recent':[self.event(10)], 'pending_count':1, 'save_failed':True})
        self.disk.fail = False
        await self.journal.async_flush(30)
        await self.journal.async_flush(30)
        self.assertEqual(self.disk.data['events'], [self.event(10), self.event(20)])
        self.assertFalse(self.journal.overview('hp')['save_failed'])

    async def test_restart_reads_committed_only(self):
        self.journal.append(self.event(10))
        await self.journal.async_flush(10)
        self.journal.append(self.event(20))
        restored = EventJournal(self.disk, 'end', 3, 1000)
        await restored.async_load()
        self.assertEqual(restored.overview('hp')['recent'], [self.event(10)])
        self.assertEqual(restored.overview('hp')['pending_count'], 0)

    async def test_retention_and_source_isolation(self):
        for stamp in (1, 2, 3, 4):
            self.journal.append(self.event(stamp))
        await self.journal.async_flush(4)
        self.assertEqual(len(self.journal.overview('hp')['recent']), 3)
        self.journal.append(self.event(2000, 'other'))
        await self.journal.async_flush(2000)
        self.assertEqual(self.journal.overview('hp')['recent'], [])
        self.assertEqual(self.journal.overview('other')['recent'], [self.event(2000,'other')])

    async def test_invalid_load(self):
        self.disk.data = {'events':[{'end':1}]}
        with self.assertRaises(ValueError):
            await self.journal.async_load()

    async def test_isolation(self):
        event = self.event(10)
        self.journal.append(event)
        event['end'] = 20
        await self.journal.async_flush(20)
        self.journal.overview('hp')['recent'][0]['end'] = 30
        self.assertEqual(self.disk.data['events'], [self.event(10)])
        self.assertEqual(self.journal.overview('hp')['recent'], [self.event(10)])

    async def test_mode_timestamp(self):
        journal = EventJournal(self.disk, 'observed_at', 3)
        journal.append({'source_id':'hp','observed_at':10,'mode':'heating'})
        await journal.async_flush(10)
        self.assertEqual(journal.overview('hp')['recent'][0]['mode'], 'heating')
