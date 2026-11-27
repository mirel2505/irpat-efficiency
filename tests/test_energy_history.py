import unittest
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from custom_components.irpat_efficiency.energy_history import append_interval, meter_delta, summarize, period_dates


class EnergyHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tz = timezone.utc
        self.day = date(2026, 11, 27)
        self.start = int(datetime(2026, 11, 27, tzinfo=self.tz).timestamp())
        self.ledger = {}

    def add(self, offset, e, q=None, mode=None, confirmed=False):
        return append_interval(self.ledger, self.start+offset, self.start+offset+300, e, q,
                               timezone=self.tz, mode=mode, boundary_confirmed=confirmed)

    def summary(self, elapsed=900, tariff=None):
        return summarize(self.ledger, self.day, date(2026,11,28), timezone=self.tz,
                         now=self.start+elapsed, tariff=tariff)

    def test_weighted_cop_and_defrost(self):
        self.add(0, 1, 5, 'heating', True)
        self.add(300, 2, 6, 'heating', True)
        self.add(600, 1, -1, 'heating', True)
        r = self.summary(tariff=1.2)
        self.assertEqual(r['status'], 'complete')
        self.assertEqual(r['modes']['heating']['cop'], 2.5)
        self.assertAlmostEqual(r['estimated_cost'], 4.8)

    def test_unconfirmed_and_unknown_mode(self):
        self.add(0, 1, 4, 'heating', False)
        self.add(300, 2, 8, None, True)
        r = self.summary()
        self.assertEqual(r['electric_kwh'], 3)
        self.assertIsNone(r['modes']['heating']['cop'])

    def test_separate_modes(self):
        self.add(0, 1, 4, 'heating', True)
        self.add(300, 2, -6, 'cooling', True)
        r = self.summary()
        self.assertEqual(r['modes']['heating']['cop'], 4)
        self.assertEqual(r['modes']['cooling']['cop'], 3)

    def test_gap_and_invalid(self):
        self.add(0, 1)
        self.add(600, None)
        r = self.summary()
        self.assertEqual(r['status'], 'partial')
        self.assertAlmostEqual(r['coverage'], 1/3)

    def test_duplicate_and_out_of_order(self):
        self.assertTrue(self.add(300, 1))
        self.assertFalse(self.add(300, 9))
        self.assertFalse(self.add(0, 9))
        self.assertEqual(self.summary()['electric_kwh'], 1)

    def test_reset(self):
        self.assertIsNone(meter_delta(100, 2))
        self.assertIsNone(meter_delta(None, 2))
        self.assertEqual(meter_delta(100, 101), 1)

    def test_no_data_is_not_zero(self):
        self.assertIsNone(self.summary()['electric_kwh'])
        self.add(0, 0)
        self.assertEqual(self.summary()['electric_kwh'], 0)

    def test_dst(self):
        tz = ZoneInfo('Europe/Bucharest')
        for first, stop, hours in [(date(2026,3,29),date(2026,3,30),23),
                                   (date(2026,10,25),date(2026,10,26),25)]:
            end = datetime(stop.year,stop.month,stop.day,tzinfo=tz).timestamp()
            self.assertEqual(summarize({},first,stop,timezone=tz,now=end)['expected_seconds'],hours*3600)

    def test_periods(self):
        p = period_dates(self.day)
        self.assertEqual(p['weekly'][0], date(2026,11,23))
        self.assertEqual(p['monthly'][0], date(2026,11,1))
        self.assertEqual(p['annual'][0], date(2026,1,1))

    def test_day_boundary(self):
        self.add(86100, 1)
        self.add(86400, 2)
        self.assertEqual(self.ledger['days']['2026-11-27']['electric_kwh'], 1)
        self.assertEqual(self.ledger['days']['2026-11-28']['electric_kwh'], 2)

    def test_no_future_cutoff(self):
        self.add(300, 1)
        with self.assertRaises(ValueError):
            self.summary(elapsed=0)
