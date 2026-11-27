"""Persistent observed electricity consumption, independent of HA runtime."""
import asyncio
from collections import Counter
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
            counts = Counter(s['entity_id'] for s in samples.values())
            for sid, sample in samples.items():
                entity = sample['entity_id']
                if counts[entity] > 1:
                    continue
                signature = [entity, str(timezone)]
                segments = prospective.setdefault(sid, [])
                if not segments or segments[-1]['signature'] != signature:
                    segments.append({'signature': signature, 'ledger': {}})
                segment = segments[-1]
                ledger = segment['ledger']
                pair_signature = sample.get('pair_signature')
                pairs = segment.setdefault('pair_segments', [])
                if not pairs or pairs[-1]['signature'] != pair_signature:
                    pairs.append({'signature': deepcopy(pair_signature), 'ledger': {}})
                v, t = sample.get('value'), sample.get('timestamp')
                if (sample.get('status') != 'reported' or not finite(v) or v < 0
                        or not finite(t) or not 0 <= now-t <= 60 or now-slot > 60):
                    continue
                old = self.baselines.get(sid)
                if old and old['signature'] == signature and old['slot'] == slot-SLOT and t > old['timestamp']:
                    delta = meter_delta(old['value'], v)
                    append_interval(ledger, slot-SLOT, slot, delta, None, timezone=timezone)
                    if pair_signature is not None and old.get('pair_signature') == pair_signature:
                        mode, heat = matched_heat(old, sample)
                        if mode is not None:
                            append_interval(pairs[-1]['ledger'], slot-SLOT, slot, delta, heat,
                                            timezone=timezone, mode=mode, boundary_confirmed=True)
                baselines[sid] = {'signature': signature, 'slot': slot, 'value': v, 'timestamp': t,
                                  'pair': deepcopy(sample.get('pair')),
                                  'pair_signature': deepcopy(pair_signature)}
            # On failure do not advance baselines or publish unpersisted totals.
            if prospective != self.data:
                await self.store.async_save({'sources': deepcopy(prospective)})
                self.data = prospective
            self.baselines = baselines

    def overview(self, samples, now, timezone):
        dates = period_dates(datetime.fromtimestamp(now, timezone).date())
        result = {}
        counts = Counter(s['entity_id'] for s in samples.values())
        for sid, sample in samples.items():
            segments = self.data.get(sid, [])
            signature = [sample['entity_id'], str(timezone)]
            shared = counts[sample['entity_id']] > 1
            segment = segments[-1] if not shared and segments and segments[-1]['signature'] == signature else {}
            ledger = segment.get('ledger', {})
            pairs = segment.get('pair_segments', [])
            pair_signature = sample.get('pair_signature')
            pair_ledger = pairs[-1]['ledger'] if pair_signature is not None and pairs and pairs[-1]['signature'] == pair_signature else {}
            result[sid] = {}
            for name, (first, stop) in dates.items():
                row = summarize(ledger, first, stop, timezone=timezone, now=now)
                # Do not reuse legacy unversioned ratios or mix measurement configurations.
                row['modes'] = summarize(pair_ledger, first, stop, timezone=timezone, now=now)['modes']
                if shared:
                    row['status'] = 'shared_meter'
                result[sid][name] = row
        return result

    async def async_close(self):
        async with self.lock:
            self.closed = True
