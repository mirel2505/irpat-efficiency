"""Monitor integration tests with a simulated HA state machine, clock and disk."""
import importlib
import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

PACKAGE = 'custom_components.irpat_efficiency.'


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


class MonitorAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stamp = 10000
        self.disk = Disk()
        self.cancelled = 0
        self.hass = SimpleNamespace(states={})
        self.topology = {'sources': [{'id':'hp','source_type':'heat_pump',
                                      'energy_boundary_confirmed':True,
                                      'mode_binding': {'entity_id':'sensor.mode','mapping':{'h':'heating','d':'dhw'}}}],
                         'telemetry':[{'group':'sources','owner_id':'hp','role':r,'entity_id':e}
                                      for r,e in [('defrost','binary_sensor.defrost'),
                                                  ('electrical_energy','sensor.energy'),
                                                  ('supply_temperature','sensor.supply')]]}
        self.entry = SimpleNamespace(entry_id='test',options={'topology':self.topology})
        names = ['homeassistant','homeassistant.helpers','homeassistant.helpers.event',
                 'homeassistant.helpers.storage','homeassistant.util','homeassistant.util.dt',
                 PACKAGE+'topology']
        modules = {name:ModuleType(name) for name in names}
        modules['homeassistant.helpers.event'].async_track_time_interval = lambda *args: self.cancel
        modules['homeassistant.helpers.storage'].Store = lambda *args: self.disk
        modules['homeassistant.util.dt'].utcnow = self.now
        modules['homeassistant.util'].dt = modules['homeassistant.util.dt']
        # Only the empty default is stubbed; every test supplies the actual topology structure.
        modules[PACKAGE+'topology'].empty_topology = lambda: {'sources': [], 'telemetry': []}
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        for name in ('telemetry_reader','mode_monitor','defrost_monitor'):
            sys.modules.pop(PACKAGE+name, None)
        self.defrost = importlib.import_module(PACKAGE+'defrost_monitor').DefrostMonitor
        self.modes = importlib.import_module(PACKAGE+'mode_monitor').ModeMonitor

    def cancel(self):
        self.cancelled += 1

    def now(self):
        return datetime.fromtimestamp(self.stamp, timezone.utc)

    def state(self, entity, value, unit=None, age=0, changed=None):
        timestamp = datetime.fromtimestamp(self.stamp-age, timezone.utc)
        self.hass.states[entity] = SimpleNamespace(state=str(value), attributes={'unit_of_measurement':unit},
            last_reported=timestamp,last_updated=timestamp,
            last_changed=datetime.fromtimestamp(changed if changed is not None else self.stamp-age,timezone.utc))

    async def sample_defrost(self, monitor, active, energy, age=0):
        self.state('binary_sensor.defrost', 'on' if active else 'off')
        self.state('sensor.energy',energy,'kWh',age=age)
        self.state('sensor.supply',30,'°C')
        await monitor.async_sample(self.now())
        self.stamp += 30

    async def test_defrost_retry_on_stop(self):
        monitor = self.defrost(self.hass,self.entry)
        await monitor.async_start()
        await self.sample_defrost(monitor,False,10)
        await self.sample_defrost(monitor,True,10.1)
        self.disk.fail=True
        with self.assertLogs(level='ERROR'):
            await self.sample_defrost(monitor,False,10.2)
        row=monitor.overview(self.topology)['hp']
        self.assertEqual(row['recent'],[])
        self.assertEqual(row['pending_count'],1)
        self.disk.fail=False
        await monitor.async_stop()
        self.assertEqual(self.cancelled,1)
        self.assertEqual(len(self.disk.data['events']),1)
        self.assertAlmostEqual(self.disk.data['events'][0]['electric_kwh'],.1)
        restored=self.defrost(self.hass,self.entry)
        await restored.async_start()
        self.assertEqual(restored.overview(self.topology)['hp']['pending_count'],0)
        self.assertEqual(len(restored.overview(self.topology)['hp']['recent']),1)
        await restored.async_stop()

    async def test_shared_meter_excludes_energy(self):
        self.topology['sources'].append({'id':'gas','source_type':'gas'})
        self.topology['telemetry'].append({'group':'sources','owner_id':'gas','role':'electrical_energy','entity_id':'sensor.energy'})
        monitor=self.defrost(self.hass,self.entry)
        await monitor.async_start()
        for active,e in [(False,10),(True,10.1),(False,10.2)]:
            await self.sample_defrost(monitor,active,e)
        row=monitor.overview(self.topology)
        self.assertNotIn('gas',row)
        self.assertEqual(len(row['hp']['recent']),1)
        self.assertIsNone(row['hp']['recent'][0]['electric_kwh'])
        await monitor.async_stop()

    async def test_stale_energy_does_not_count_as_zero(self):
        monitor=self.defrost(self.hass,self.entry)
        await monitor.async_start()
        for active,e in [(False,10),(True,10.1),(False,10.2)]:
            await self.sample_defrost(monitor,active,e,age=120)
        self.assertIsNone(monitor.overview(self.topology)['hp']['recent'][0]['electric_kwh'])
        await monitor.async_stop()

    async def test_mode_journal_retries_without_duplicate(self):
        monitor=self.modes(self.hass,self.entry)
        await monitor.async_start()
        self.state('sensor.mode','h',changed=9990)
        await monitor.async_sample(self.now())
        self.stamp+=30
        self.state('sensor.mode','d',changed=self.stamp)
        self.disk.fail=True
        with self.assertLogs(level='ERROR'):
            await monitor.async_sample(self.now())
        row=monitor.overview(self.topology)['hp']
        self.assertEqual([e['mode'] for e in row['recent']],['heating'])
        self.assertEqual(row['pending_count'],1)
        self.stamp+=30
        self.disk.fail=False
        await monitor.async_sample(self.now())
        await monitor.async_stop()
        self.assertEqual([e['mode'] for e in self.disk.data['events']],['heating','dhw'])
