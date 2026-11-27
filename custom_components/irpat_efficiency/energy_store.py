"""Persistent observed electricity consumption, independent of HA runtime."""
import asyncio
from copy import deepcopy
from datetime import datetime

from .energy_history import SLOT, append_interval, finite, meter_delta, period_dates, summarize
from .paired_energy import matched_heat


class EnergyStore:
    def __init__(self, store):
        self.store = store
        self.data = {}
        self.baselines = {}
        self.lock = asyncio.Lock()
        self.closed = False

    async def async_load(self):
        saved = await self.store.async_load()
        if saved is not None:
            if not isinstance(saved, dict) or not isinstance(saved.get('sources'), dict):
                raise ValueError('invalid_energy_history')
            self.data = deepcopy(saved['sources'])

    async def async_sample(self, samples, now, timezone):
        """Use only consecutive, fresh meter reports; no interpolation after restart.

        Samples are keyed by source ID. Each contains entity_id, value (kWh),
        timestamp (UTC seconds) and status. Calendar totals are approximate
        allocations to five-minute slots; report age must be at most 60 seconds.
        A changed meter or timezone starts a separate ledger segment.
        """
        async with self.lock:
            if self.closed:
                return
            slot = int(now)//SLOT*SLOT
            prospective = deepcopy(self.data)
            baselines = {}
            for sid, sample in samples.items():
                entity = sample['entity_id']
                signature = [entity, str(timezone)]
                segments = prospective.setdefault(sid, [])
                if not segments or segments[-1]['signature'] != signature:
                    segments.append({'signature': signature, 'ledger': {}})
                ledger = segments[-1]['ledger']
                v, t = sample.get('value'), sample.get('timestamp')
                if (sample.get('status') != 'reported' or not finite(v) or v < 0
                        or not finite(t) or not 0 <= now-t <= 60 or now-slot > 60):
                    continue
                old = self.baselines.get(sid)
                if old and old['signature'] == signature and old['slot'] == slot-SLOT and t > old['timestamp']:
                    delta = meter_delta(old['value'], v)
                    mode, heat = matched_heat(old, sample)
                    append_interval(ledger, slot-SLOT, slot, delta, heat, timezone=timezone,
                                    mode=mode, boundary_confirmed=mode is not None)
                baselines[sid] = {'signature': signature, 'slot': slot, 'value': v, 'timestamp': t,
                                  'pair': deepcopy(sample.get('pair'))}
            # On failure do not advance baselines or publish unpersisted totals.
            if prospective != self.data:
                await self.store.async_save({'sources': deepcopy(prospective)})
                self.data = prospective
            self.baselines = baselines

    def overview(self, samples, now, timezone):
        dates = period_dates(datetime.fromtimestamp(now, timezone).date())
        result = {}
        for sid, sample in samples.items():
            segments = self.data.get(sid, [])
            signature = [sample['entity_id'], str(timezone)]
            ledger = segments[-1]['ledger'] if segments and segments[-1]['signature'] == signature else {}
            result[sid] = {name: summarize(ledger, first, stop, timezone=timezone, now=now)
                           for name, (first, stop) in dates.items()}
        return result

    async def async_close(self):
        async with self.lock:
            self.closed = True
