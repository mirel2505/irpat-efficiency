"""Append-only journal with durable, serialized writes via an injected store."""
from copy import deepcopy
import asyncio

from .journal import make_snapshot


class HydraulicJournal:
    def __init__(self, store):
        self.store = store
        self.entries = []
        self.lock = asyncio.Lock()
        self.closed = False

    async def async_load(self):
        data = await self.store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
                raise ValueError("invalid_journal")
            self.entries = data["entries"]

    def recent(self, limit=100):
        return deepcopy(self.entries[-limit:])

    async def async_append(self, topology, manifold_id, readings, *, previous_id=None,
                           context=None, **kwargs):
        async with self.lock:
            if self.closed:
                raise ValueError("journal_closed")
            previous = next((s for s in self.entries if s["id"] == previous_id), None)
            if previous_id is not None and previous is None:
                raise ValueError("missing_before")
            snapshot = make_snapshot(topology, manifold_id, readings, previous=previous, **kwargs)
            snapshot["context"] = deepcopy(context or {})
            updated = [*self.entries, snapshot]
            await self.store.async_save({"entries": updated})
            self.entries = updated
            return deepcopy(snapshot)

    async def async_close(self):
        async with self.lock:
            self.closed = True
