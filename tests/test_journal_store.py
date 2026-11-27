"""Exercise persistence without requiring Home Assistant."""
import asyncio
from copy import deepcopy
import unittest

from custom_components.irpat_efficiency.journal_store import HydraulicJournal


class FakeStore:
    def __init__(self):
        self.data = None
        self.fail = False

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        await asyncio.sleep(0)
        if self.fail:
            raise OSError("disk failure")
        self.data = deepcopy(data)


class JournalStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = FakeStore()
        self.journal = HydraulicJournal(self.store)
        await self.journal.async_load()
        self.topology = {"manifolds": [{"id": "m"}], "circuits": [{"id": "a", "manifold_id": "m"}]}

    async def append(self, **kwargs):
        return await self.journal.async_append(self.topology, "m", {"a": 1.0}, **kwargs)

    async def test_reload_and_reference(self):
        before = await self.append(phase="before")
        restored = HydraulicJournal(self.store)
        await restored.async_load()
        after = await restored.async_append(self.topology, "m", {"a": 0.8}, phase="after", previous_id=before["id"])
        self.assertEqual(after["previous_id"], before["id"])
        self.assertEqual(len(restored.recent()), 2)

    async def test_concurrent_writes(self):
        await asyncio.gather(self.append(), self.append())
        self.assertEqual(len(self.store.data["entries"]), 2)

    async def test_failed_save(self):
        self.store.fail = True
        with self.assertRaises(OSError):
            await self.append()
        self.assertEqual(self.journal.recent(), [])

    async def test_bad_reference_and_closed(self):
        with self.assertRaises(ValueError):
            await self.append(phase="after", previous_id="missing")
        await self.journal.async_close()
        with self.assertRaises(ValueError):
            await self.append()

    async def test_immutable_context(self):
        context = {"room": 22}
        result = await self.append(context=context)
        context["room"] = 24
        result["context"]["room"] = 25
        self.assertEqual(self.journal.recent()[0]["context"]["room"], 22)
