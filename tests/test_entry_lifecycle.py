"""Exercise actual integration entry lifecycle with injected simulated components."""
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import custom_components.irpat_efficiency as integration


class EntryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.start_fail = None
        self.stop_fail = None
        self.hass = SimpleNamespace(data={})
        self.entry = SimpleNamespace(entry_id='entry')
        self.components = (
            ('report_store','ReportStore','report_stores'),
            ('journal_store','HydraulicJournal','journals'),
            ('profile_store','ProfileStore','profiles'),
            ('history_store','RoomHistory','histories'),
            ('defrost_monitor','DefrostMonitor','defrost_monitors'),
            ('energy_monitor','EnergyMonitor','energy_monitors'),
            ('mode_monitor','ModeMonitor','mode_monitors'),
        )
        modules = {name:ModuleType(name) for name in ('homeassistant','homeassistant.helpers','homeassistant.helpers.storage')}
        modules['homeassistant.helpers.storage'].Store = lambda *args: object()
        for module, cls, key in self.components:
            path = integration.__name__+'.'+module
            modules[path] = ModuleType(path)
            setattr(modules[path], cls, self.factory(key))
        panel = SimpleNamespace(async_register=self.register, async_remove=self.remove)
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(integration,'panel',panel,create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def factory(self,key):
        async def start():
            self.calls.append(('start',key))
            if self.start_fail == key:
                raise RuntimeError('start failed')
        async def stop():
            self.calls.append(('stop',key))
            if self.stop_fail == key:
                raise RuntimeError('stop failed')
        return lambda *args: SimpleNamespace(async_load=start,async_start=start,async_close=stop,async_stop=stop)

    async def register(self,hass):
        self.calls.append(('register','panel'))
        if self.start_fail == 'panel':
            raise RuntimeError('start failed')

    def remove(self,hass):
        self.calls.append(('remove','panel'))

    async def test_partial_start_rollback(self):
        self.start_fail = 'histories'
        with self.assertRaisesRegex(RuntimeError,'start failed'):
            await integration.async_setup_entry(self.hass,self.entry)
        self.assertEqual([k for action,k in self.calls if action=='stop'],
                         ['histories','profiles','journals','report_stores'])
        self.assertFalse(self.hass.data[integration.DOMAIN]['active_entries'])

    async def test_panel_failure_rolls_back_all(self):
        self.start_fail='panel'
        with self.assertRaisesRegex(RuntimeError,'start failed'):
            await integration.async_setup_entry(self.hass,self.entry)
        self.assertEqual([k for action,k in self.calls if action=='stop'],
                         [k for _,_,k in reversed(self.components)])

    async def test_unload_continues_and_retries_failed_component(self):
        self.assertTrue(await integration.async_setup_entry(self.hass,self.entry))
        self.stop_fail='mode_monitors'
        with self.assertLogs(level='ERROR'):
            self.assertFalse(await integration.async_unload_entry(self.hass,self.entry))
        self.assertEqual([k for action,k in self.calls if action=='stop'],
                         [k for _,_,k in reversed(self.components)])
        self.assertIn('entry',self.hass.data[integration.DOMAIN]['mode_monitors'])
        self.stop_fail=None
        self.assertTrue(await integration.async_unload_entry(self.hass,self.entry))
        self.assertNotIn('entry',self.hass.data[integration.DOMAIN]['active_entries'])
        self.assertEqual(self.calls[-2:],[('stop','mode_monitors'),('remove','panel')])

    async def test_reload_no_duplicate_components(self):
        self.assertTrue(await integration.async_setup_entry(self.hass,self.entry))
        self.assertFalse(await integration.async_setup_entry(self.hass,self.entry))
        self.assertTrue(await integration.async_unload_entry(self.hass,self.entry))
        self.assertTrue(await integration.async_setup_entry(self.hass,self.entry))
        self.assertTrue(await integration.async_unload_entry(self.hass,self.entry))
        self.assertEqual(sum(action=='start' for action,_ in self.calls),14)
        self.assertEqual(sum(action=='stop' for action,_ in self.calls),14)
