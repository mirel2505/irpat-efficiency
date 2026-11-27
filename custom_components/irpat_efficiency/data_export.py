"""Versioned, read-only exports of committed irPaT data; not a restore format."""
import csv
import io
import json
from copy import deepcopy
from datetime import datetime, timezone

EXPORT_VERSION = 1
MAX_BYTES = 4 * 1024 * 1024
CSV_SECTIONS = ('temperatures', 'energy', 'hydraulics', 'profiles', 'observations',
                'comparisons', 'defrost', 'modes')


def capture(entry_id, name, topology, runtime, now):
    """Capture one entry synchronously, without yielding between published stores."""
    if entry_id not in runtime.get('active_entries', set()):
        raise ValueError('inactive_entry')
    def get(key):
        return runtime[key][entry_id]
    history, energy = get('histories'), get('energy_monitors')
    defrost, modes = get('defrost_monitors').journal, get('mode_monitors').journal
    reports = get('report_stores').data
    return deepcopy({
        'format': 'irpat_efficiency.export', 'version': EXPORT_VERSION,
        'exported_at_utc': datetime.fromtimestamp(now, timezone.utc).isoformat(),
        'entry_id': entry_id, 'name': name, 'topology': topology,
        'restore_supported': False,
        'temperature_history': {'rooms': history.data,
                                'configuration_hash': history.configuration_hash,
                                'configuration_since': history.configuration_since,
                                'matches_current_configuration': history.configuration_hash == history.fingerprint(topology)},
        'energy_history': energy.history.data,
        'hydraulics': get('journals').entries, 'profiles': get('profiles').profiles,
        'observations': reports['observations'], 'comparisons': reports['reports'],
        'defrost': defrost.committed, 'modes': modes.committed,
        'storage_status': {'temperature_save_failed': history.save_failed,
                           'energy_save_failed': energy.save_failed,
                           'defrost_save_failed': defrost.save_failed,
                           'mode_save_failed': modes.save_failed,
                           'defrost_pending_excluded': len(defrost.pending),
                           'mode_pending_excluded': len(modes.pending)},
    })


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list, tuple)):
        value = _json(value)
    if isinstance(value, str) and (value.startswith(('\t', '\r', '\n')) or
                                   value.lstrip().startswith(('=', '+', '-', '@'))):
        return "'" + value
    return value


def _rows(snapshot, section):
    if section == 'temperatures':
        h = snapshot['temperature_history']
        since = h['configuration_since']
        for rid, samples in h['rooms'].items():
            for stamp, value in sorted(samples.items(), key=lambda item: int(item[0])):
                yield {'room_id': rid, 'timestamp_utc': datetime.fromtimestamp(int(stamp), timezone.utc).isoformat(),
                       'temperature_c': value, 'current_configuration': bool(h['matches_current_configuration'] and
                           since is not None and int(stamp) >= since)}
    elif section == 'energy':
        for sid, segments in snapshot['energy_history'].items():
            for i, seg in enumerate(segments):
                for day, row in sorted(seg['ledger'].get('days', {}).items()):
                    yield {'source_id': sid, 'meter_segment': i, 'pair_segment': None,
                           'meter_signature': seg['signature'], 'pair_signature': None,
                           'local_date': day, 'kind': 'electric_total', 'mode': None,
                           'electric_kwh': row['electric_kwh'] if row['electric_seconds'] else None,
                           'thermal_kwh': None, 'observed_seconds': row['electric_seconds']}
                for j, pair in enumerate(seg.get('pair_segments', [])):
                    for day, row in sorted(pair['ledger'].get('days', {}).items()):
                        for mode, m in row['modes'].items():
                            yield {'source_id': sid, 'meter_segment': i, 'pair_segment': j,
                                   'meter_signature': seg['signature'], 'pair_signature': pair['signature'],
                                   'local_date': day, 'kind': 'matched_subset', 'mode': mode,
                                   'electric_kwh': m['electric_kwh'], 'thermal_kwh': m['thermal_kwh'],
                                   'observed_seconds': m['seconds']}
    elif section == 'hydraulics' or section == 'profiles':
        for record in snapshot[section]:
            base = {key: value for key, value in record.items() if key not in ('flows_lmin', 'context')}
            for cid, flow in record['flows_lmin'].items():
                yield {**base, 'circuit_id': cid, 'flow_lmin': flow}
    else:
        yield from snapshot[section]


def serialize(snapshot, format, section=None):
    """Return bounded UTF-8 text, escaping spreadsheet formula-like strings."""
    if format == 'json' and section is None:
        text = _json(snapshot)
        mime, suffix = 'application/json', 'json'
    elif format == 'csv' and section in CSV_SECTIONS:
        rows = list(_rows(snapshot, section))
        # Include a header even when the section has no observations.
        fields = list(dict.fromkeys(k for row in rows for k in row)) or ['no_records']
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\r\n')
        writer.writerow({key: _cell(key) for key in fields})
        for row in rows:
            writer.writerow({key: _cell(value) for key, value in row.items()})
        text = '\ufeff' + stream.getvalue()
        mime, suffix = 'text/csv', f'{section}.csv'
    else:
        raise ValueError('invalid_export_format')
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('export_too_large')
    return {'filename': 'irpat-export.' + suffix, 'mime': mime, 'content': text,
            'storage_status': deepcopy(snapshot['storage_status'])}
