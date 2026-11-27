"""Persistent reviewed building observations and intervention comparisons."""
import asyncio
from copy import deepcopy
from uuid import uuid4

from .building_report import snapshot, compare


def _label(value, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError('invalid_label')
    return value.strip()


class ReportStore:
    """Injected async store; publish changes only after persistence succeeds."""
    def __init__(self, store):
        self.store = store
        self.data = {'observations': [], 'reports': []}
        self.lock = asyncio.Lock()
        self.closed = False

    async def async_load(self):
        saved = await self.store.async_load()
        if saved is not None:
            if not isinstance(saved, dict) or any(not isinstance(saved.get(k), list) for k in self.data):
                raise ValueError('invalid_report_store')
            self.data = deepcopy(saved)

    def overview(self):
        return deepcopy(self.data)

    async def async_capture(self, name, indoor, outdoor, start, end, *,
                            measurement_signature, note='', **kwargs):
        async with self.lock:
            if self.closed:
                raise ValueError('store_closed')
            if not isinstance(measurement_signature, str) or not measurement_signature.strip():
                raise ValueError('invalid_measurement_signature')
            item = snapshot(indoor, outdoor, start, end, **kwargs)
            item.update(name=_label(name), measurement_signature=measurement_signature,
                        note=_label(note, 2000) if note else '')
            data = deepcopy(self.data)
            data['observations'].append(item)
            await self.store.async_save(deepcopy(data))
            self.data = data
            return deepcopy(item)

    async def async_compare(self, before_id, after_id, *, name, intervention_at,
                            comparable=False, note=''):
        async with self.lock:
            if self.closed:
                raise ValueError('store_closed')
            items = {i['id']: i for i in self.data['observations']}
            if before_id not in items or after_id not in items or before_id == after_id:
                raise ValueError('invalid_reference')
            before, after = items[before_id], items[after_id]
            if before['measurement_signature'] != after['measurement_signature']:
                raise ValueError('incompatible_measurements')
            result = compare(before, after, intervention_at=intervention_at, comparable=comparable)
            result.update(id=uuid4().hex, name=_label(name), note=_label(note, 2000) if note else '')
            data = deepcopy(self.data)
            data['reports'].append(result)
            await self.store.async_save(deepcopy(data))
            self.data = data
            return deepcopy(result)

    async def async_close(self):
        async with self.lock:
            self.closed = True
