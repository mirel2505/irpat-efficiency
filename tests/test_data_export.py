import csv
import io
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from custom_components.irpat_efficiency.data_export import capture, serialize, CSV_SECTIONS


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.topology = {'rooms': [{'id': 'r', 'name': 'Cameră'}]}
        self.runtime = {'active_entries': {'e'}}
        objects = {
            'histories': NS(data={'r': {'0': 21, '300': 22}}, configuration_hash='a',
                            configuration_since=300, fingerprint=lambda t: 'a', save_failed=False),
            'energy_monitors': NS(history=NS(data={'s': [{'signature': ['sensor.e', 'UTC'],
                'ledger': {'days': {'1970-01-01': {'electric_kwh': 2, 'electric_seconds': 300, 'modes': {}}}},
                'pair_segments': [{'signature': {'meter': 'sensor.q'}, 'ledger': {'days': {'1970-01-01': {
                    'modes': {'heating': {'electric_kwh': .5, 'thermal_kwh': 2, 'seconds': 300}}}}}}]}]}), save_failed=False),
            'journals': NS(entries=[{'id': 'j', 'note': ' =1+1', 'flows_lmin': {'c': 0.0}, 'context': {'private': 'context'}}]),
            'profiles': NS(profiles=[{'id': 'p', 'flows_lmin': {'c': 1.2}}]),
            'report_stores': NS(data={'observations': [{'id': 'o', 'name': 'Cameră', 'thermal_kwh': 48}],
                                      'reports': [{'id': 'q', 'normalized_change_pct': -10}]}),
            'defrost_monitors': NS(journal=NS(committed=[{'source_id': 's', 'end': 300}], pending=[{'end': 600}], save_failed=True)),
            'mode_monitors': NS(journal=NS(committed=[], pending=[], save_failed=False)),
        }
        self.runtime.update({k: {'e': v} for k, v in objects.items()})
        self.snapshot = capture('e', 'Test', self.topology, self.runtime, 600)

    def rows(self, section):
        result = serialize(self.snapshot, 'csv', section)
        self.assertTrue(result['content'].startswith('\ufeff'))
        return list(csv.DictReader(io.StringIO(result['content'].lstrip('\ufeff'))))

    def test_json_version_and_unicode(self):
        result = json.loads(serialize(self.snapshot, 'json')['content'])
        self.assertEqual(result, self.snapshot)
        self.assertEqual(result['version'], 1)
        self.assertFalse(result['restore_supported'])
        self.assertEqual(result['topology']['rooms'][0]['name'], 'Cameră')

    def test_only_committed_and_warnings(self):
        self.assertEqual(len(self.snapshot['defrost']), 1)
        self.assertEqual(self.snapshot['storage_status']['defrost_pending_excluded'], 1)
        self.assertTrue(serialize(self.snapshot, 'json')['storage_status']['defrost_save_failed'])

    def test_capture_does_not_modify_live_data(self):
        self.snapshot['topology']['rooms'].clear()
        self.snapshot['hydraulics'][0]['flows_lmin']['c'] = 9
        self.assertEqual(len(self.topology['rooms']), 1)
        self.assertEqual(self.runtime['journals']['e'].entries[0]['flows_lmin']['c'], 0)

    def test_all_csv_sections(self):
        for section in CSV_SECTIONS:
            with self.subTest(section=section):
                self.rows(section)
        self.assertEqual(self.rows('modes'), [])

    def test_csv_formula_escape_and_numeric_values(self):
        rows = self.rows('hydraulics')
        self.assertEqual(rows[0]['note'], "' =1+1")
        self.assertEqual(rows[0]['flow_lmin'], '0.0')
        self.assertEqual(self.rows('comparisons')[0]['normalized_change_pct'], '-10')
        for value in ('=1', '+1', '-1', '@x', '\tfoo', '\rfoo', '\nfoo'):
            self.snapshot['observations'][0]['name'] = value
            self.assertEqual(self.rows('observations')[0]['name'], "'" + value)

    def test_energy_segments_are_not_summed(self):
        rows = self.rows('energy')
        self.assertEqual([r['kind'] for r in rows], ['electric_total', 'matched_subset'])
        self.assertEqual([r['electric_kwh'] for r in rows], ['2', '0.5'])
        self.assertEqual(rows[1]['thermal_kwh'], '2')

    def test_temperature_epoch(self):
        self.assertEqual([r['current_configuration'] for r in self.rows('temperatures')], ['False', 'True'])

    def test_invalid_and_size_limit(self):
        with self.assertRaisesRegex(ValueError, 'inactive_entry'):
            capture('other', 'Test', self.topology, self.runtime, 600)
        with self.assertRaisesRegex(ValueError, 'invalid_export_format'):
            serialize(self.snapshot, 'csv', 'unknown')
        with patch('custom_components.irpat_efficiency.data_export.MAX_BYTES', 10):
            with self.assertRaisesRegex(ValueError, 'export_too_large'):
                serialize(self.snapshot, 'json')

    def test_no_nan_in_json(self):
        self.snapshot['observations'][0]['thermal_kwh'] = float('nan')
        with self.assertRaises(ValueError):
            serialize(self.snapshot, 'json')
