"""Bounded event persistence; callers serialize access with their monitor lock."""
from copy import deepcopy
from math import isfinite


class EventJournal:
    def __init__(self, store, time_key, limit, retention_seconds=30*86400):
        self.store = store
        self.time_key = time_key
        self.limit = limit
        self.retention_seconds = retention_seconds
        self.committed = []
        self.pending = []
        self.save_failed = False

    def _valid(self, event):
        if not isinstance(event, dict) or not isinstance(event.get('source_id'), str):
            return False
        stamp = event.get(self.time_key)
        return type(stamp) in (int, float) and isfinite(stamp)

    async def async_load(self):
        data = await self.store.async_load()
        if data is None:
            return
        if (not isinstance(data, dict) or not isinstance(data.get('events'), list)
                or not all(self._valid(e) for e in data['events'])):
            raise ValueError('invalid_event_history')
        self.committed = deepcopy(data['events'])

    def append(self, event):
        if not self._valid(event):
            raise ValueError('invalid_event')
        self.pending.append(deepcopy(event))

    async def async_flush(self, now):
        if type(now) not in (int, float) or not isfinite(now):
            raise ValueError('invalid_timestamp')
        # Bound unsaved observations too; retention applies even during a disk failure.
        self.pending = [e for e in self.pending if e[self.time_key] >= now-self.retention_seconds][-self.limit:]
        events = [e for e in self.committed + self.pending
                  if e[self.time_key] >= now-self.retention_seconds][-self.limit:]
        if events != self.committed or self.pending:
            try:
                await self.store.async_save({'events': deepcopy(events)})
            except Exception:
                self.save_failed = True
                raise
            self.committed = events
            self.pending = []
        self.save_failed = False

    def overview(self, source_id):
        return {'recent': deepcopy([e for e in self.committed if e['source_id'] == source_id][-20:]),
                'pending_count': sum(e['source_id'] == source_id for e in self.pending),
                'save_failed': self.save_failed}
