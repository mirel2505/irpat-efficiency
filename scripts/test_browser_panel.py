"""Real Chromium rendering and interaction with deterministic mock HA responses.

The backend is mocked here; real Core WebSocket behavior is tested separately.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

PANEL = Path(__file__).resolve().parents[1] / "custom_components/irpat_efficiency/frontend/panel.js"

FIXTURE = {
    "entry_id": "test", "name": "Test installation",
    "topology": {
        "floors": [{"id": "f", "name": "Ground"}],
        "zones": [{"id": "z", "name": "Zone"}],
        "rooms": [{"id": "r", "name": "Bedroom <script>not markup</script>", "floor_id": "f",
                   "heating_target_c": 22, "cooling_target_c": 25}],
        "manifolds": [{"id": "m", "name": "Manifold", "floor_id": "f", "zone_id": "z"}],
        "circuits": [{"id": "c", "name": "Loop", "position": 1, "room_id": "r", "manifold_id": "m"}],
        "sources": [{"id": "s", "name": "Heat pump", "source_type": "heat_pump"}],
        "outdoor_entity_id": "sensor.test_outdoor",
    },
    "room_temperatures": {"r": {
        "readings": [{"name": "Sensor", "temperature_c": 21.5, "age_seconds": 20, "status": "reported"}],
        "heating": {"temperature_c": 21.5, "deviation_c": -0.5, "status": "cold", "valid_count": 1, "configured_count": 1},
        "cooling": {"temperature_c": 21.5, "deviation_c": -3.5, "status": "cold", "valid_count": 1, "configured_count": 1}}},
    "journal": [{"id": "j", "manifold_id": "m", "timestamp": "2026-11-26T12:00:00Z",
                 "phase": "observation", "flows_lmin": {"c": 0}, "manifold_total_lmin": 0,
                 "source_total_m3h": None, "note": "Manual observation"}],
    "profiles": [{"id": "p", "name": "Reference profile", "mode": "heating",
                  "created_at": "2026-11-26T12:00:00Z", "flows_lmin": {"c": 1.2},
                  "references": {"m": {"snapshot_id": "j", "circuit_ids": ["c"]}}}],
    "live_diagnostics": {"sources": {"s": {"delta_t_c": 5, "thermal_measured_w": 3000,
                          "thermal_calculated_w": 2900, "electrical_w": 800,
                          "signed_power_ratio": 3.75, "cop_status": "observed_signed_ratio"}}},
    "energy_history": {"s": {"daily": {"electric_kwh": 8.25, "coverage": .8}}},
    "defrost": {"s": {"recent": [], "pending_count": 1, "save_failed": True}},
    "mode_history": {"s": {"recent": [{"observed_at": 1795694400, "previous_mode": "off", "mode": "heating"}],
                           "pending_count": 0, "save_failed": False}},
    "thermal_diagnostics": {}, "history": {}, "building_reports": {},
    "weather_observations": {},
}

MOCK = """({entry, language}) => {
    window.requests = [];
    const panel = document.createElement('irpat-efficiency-panel');
    panel.hass = {language, callWS: async request => {
      window.requests.push(request);
      switch(request.type) {
        case 'irpat_efficiency/overview': return [entry];
        case 'irpat_efficiency/configuration':
          entry.topology.bindings ||= [];
          return {revision:'one',topology:entry.topology,native_floors:{},native_areas:{},
                  entities:[],room_temperatures:entry.room_temperatures};
        case 'irpat_efficiency/configuration_action':
          if(request.action==='add_floor')entry.topology.floors.push({id:'newfloor',name:request.payload.name});
          return {revision:'two',topology:entry.topology,native_floors:{},native_areas:{},
                  entities:[],room_temperatures:entry.room_temperatures};
        case 'irpat_efficiency/journal_append':
          entry.journal.push({id:'new',manifold_id:request.manifold_id,
            timestamp:'2026-11-27T12:00:00Z',phase:request.phase,
            flows_lmin:request.readings,note:request.note});
          return entry.journal.at(-1);
        case 'irpat_efficiency/profile_review':
          return {rows:[{position:1,name:'Loop',reference_lmin:1.2,
                         observed_lmin:0,difference_lmin:-1.2}]};
        case 'irpat_efficiency/export_data':
          return {filename:'irpat-export.json',mime:'application/json',
                  content:JSON.stringify({format:'irpat_efficiency.export',version:1}),
                  storage_status:{}};
        default: throw new Error('Unexpected command '+request.type);
      }
    }};
    document.body.append(panel);
}"""


def run_case(browser, language, width, dark):
    context = browser.new_context(viewport={"width": width, "height": 900},
                                  color_scheme="dark" if dark else "light",
                                  accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    ro = language == "ro"
    word = lambda a, b: a if ro else b
    page.route("http://irpat.test/**", lambda route: route.fulfill(
        content_type="text/html", body="<html><body style='margin:0'></body></html>"))
    page.goto("http://irpat.test/")
    page.add_style_tag(content=":root{--primary-text-color:" + ("#eee" if dark else "#222") +
                       ";--primary-background-color:" + ("#171717" if dark else "#fafafa") +
                       ";--card-background-color:" + ("#252525" if dark else "#fff") +
                       ";--secondary-text-color:" + ("#ccc" if dark else "#555") +
                       ";--secondary-background-color:#8882;--divider-color:#8886;--primary-color:#176f9e;--text-primary-color:#fff}")
    page.add_script_tag(path=str(PANEL))
    page.evaluate(MOCK, {"entry": FIXTURE, "language": language})
    panel = page.locator("irpat-efficiency-panel")
    expect(panel.get_by_role("heading", name="Test installation", exact=True)).to_be_visible()
    expect(panel.get_by_text("21.5 °C", exact=True)).to_be_visible()
    expect(panel.get_by_role("heading", name=word("Echilibrul casei","Home comfort"), exact=True)).to_be_visible()
    expect(panel.get_by_role("heading", name=word("Următorul pas","Next step"), exact=True)).to_be_visible()
    expect(panel.get_by_text(word("Setează ținta pentru toate camerele","Set a target for all rooms"), exact=True)).to_be_visible()
    expect(panel.locator(".loop").get_by_text("0.00 l/min", exact=True)).to_be_visible()
    expect(panel.get_by_text("Bedroom <script>not markup</script>", exact=True).first).to_be_visible()
    assert panel.locator("script").count() == 0
    expect(panel.get_by_role("button", name=word("Simplu","Simple"), exact=True)).to_have_attribute("aria-pressed","true")
    # Record a zero in the actual native form; preserve its type in the payload.
    journal = panel.locator("details.journal").filter(has=page.get_by_text(
        word("Înregistrează debitele manual","Record manual flow readings"), exact=True))
    journal.locator("summary").click()
    journal.locator(".flow-fields input").first.fill("0")
    journal.get_by_role("button", name=word("Salvează observația","Save observation"), exact=True).click()
    page.wait_for_function("window.requests.some(r => r.type === 'irpat_efficiency/journal_append')")
    assert page.evaluate("window.requests.find(r=>r.type==='irpat_efficiency/journal_append').readings.c") == 0
    expect(panel.locator(".loop").get_by_text("0.00 l/min", exact=True)).to_be_visible()
    panel.get_by_role("button", name="Expert", exact=True).click()
    expect(panel.get_by_role("heading", name=word("Istoric degivrări","Defrost history"))).to_be_visible()
    expect(panel.get_by_role("heading", name=word("Istoric regimuri raportate","Reported mode history"))).to_be_visible()
    profile = panel.locator("details.journal").filter(has=page.locator("summary").filter(has_text="Reference profile"))
    profile.locator("summary").click()
    profile.get_by_role("button", name=word("Compară debitele","Compare flows")).click()
    expect(profile.get_by_text("Δ -1.20 l/min", exact=False)).to_be_visible()
    export = panel.locator("details.journal").filter(has=page.get_by_text(word("Export date","Export data"), exact=True))
    export.locator("summary").click()
    export.get_by_role("button", name=word("Pregătește exportul","Prepare export")).click()
    with page.expect_download() as event:
        export.get_by_role("link", name=word("Descarcă fișierul","Download file")).click()
    downloaded = event.value
    assert downloaded.suggested_filename == "irpat-export.json"
    assert json.loads(Path(downloaded.path()).read_text())["version"] == 1
    panel.get_by_role("button", name=word("Configurează casa","Set up home"), exact=False).click()
    expect(panel.locator(".setup")).to_be_visible()
    panel.get_by_label(word("Nume etaj nou","New floor name")).fill("New floor")
    panel.get_by_role("button", name=word("Adaugă etaj","Add floor"), exact=True).click()
    expect(panel.get_by_text("✓ "+word("Modificare salvată","Change saved"), exact=True)).to_be_visible()
    panel.get_by_role("button", name=word("Continuă →","Continue →"), exact=True).click()
    expect(panel.locator(".setup").get_by_role("heading", name=word("Camere","Rooms"), exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), "Setup horizontal overflow"
    panel.get_by_role("button", name=word("Înapoi la dashboard","Back to dashboard"), exact=True).click()
    expect(panel.get_by_role("heading", name="Test installation", exact=True)).to_be_visible()
    # The manifold itself may scroll horizontally, the document must not.
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), "Page has horizontal overflow"
    assert not errors, errors
    assert set(page.evaluate("window.requests.map(r=>r.type)")) <= {
        "irpat_efficiency/overview", "irpat_efficiency/journal_append",
        "irpat_efficiency/profile_review", "irpat_efficiency/export_data",
        "irpat_efficiency/configuration", "irpat_efficiency/configuration_action"}
    context.close()
    print(f"PASS: Chromium {language}, {width}px, {'dark' if dark else 'light'}; journal, expert, profile, download")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for args in [("ro", 390, True), ("en", 1440, False)]:
            run_case(browser, *args)
        browser.close()
