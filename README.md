# irPaT & Eficiență

**Asistență pentru echilibrarea hidraulică și termică a încălzirii și răcirii prin pardoseală cu agent termic.**

Local, advisory-only Home Assistant integration for hydronic radiant floor heating/cooling, hydraulic and thermal balancing, weather compensation, and energy efficiency.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support%20development-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/rmirel2505o)

## Stadiu / Status

**0.1.0.dev0 — experimental foundation, not ready for installation on a production system.**
Initial configuration entry, topology model, native options forms for adding floors, zones, rooms, manifolds, circuits, sources and ambient temperature bindings, and calculation primitives are implemented in source. Native forms are not yet validated on Home Assistant. An experimental administrator-only sidebar overview is implemented in source, displaying the saved topology, heating targets and graphical manifolds in physical circuit order. It uses a local dependency-free JavaScript custom element as a bootstrap; the planned TypeScript/Lit editor, full interactive manifold editing, complete configuration editing, long-term history, balancing assistant and reports are not yet implemented. An initial local history collector stores one temperature sample per room every five minutes while HA is running, independently of the panel, using HA Store. It retains eight days of recent samples, exposes 24/48/72/168-hour sample summaries and coverage, and compares yesterday's local five-minute slot. It skips incomplete room readings and HA state reports older than a provisional two-hour threshold (not necessarily actual device measurement age). No gaps are interpolated. No Recorder import or longer-term aggregates are implemented yet; these are required before release. History across sensor configuration changes needs additional validation. The overview now reads configured ambient sensor and thermostat temperatures, converts explicit units to Celsius, shows the mean of available readings and the individual heating/cooling target and deviation, and refreshes every 30 seconds while visible. Reading age is displayed, but automatic stale-data rejection in the instantaneous display and configurable sensor aggregation/tolerance remain pending. Instantaneous status is not evidence of completed balancing. Panel registration and rendering still require a real Home Assistant smoke test. Marketplace metadata (hacs.json) is present; installation has not been validated. No release is available.

The initial hydraulic journal model now validates manual loop readings, distinguishes a measured manifold total from the sum of all loops and source flow, links before/after observations, and supports conditional normalization to a comparable reference total. The experimental administrator-only panel now includes a manual flow form for each manifold, before/after references, optional manifold/source totals and notes, plus the five latest observations per manifold from the last 100 entries. The backend appends to a per-entry HA Store, serializes writes, saves before reporting success, and attaches available room readings and zone context. Automatic supply/return/outdoor readings, full journal pagination, normalization display and integration-level validation remain pending. On 2026-11-27, 16 local unit tests passed: five calculation, six hydraulic snapshot, and five journal persistence tests using an injected simulated store. The Git blob hashes of the six calculation/journal/persistence source and test files matched their repository versions. Other test modules, the actual HA Store adapter, WebSocket endpoint and browser runtime have not yet been verified in this test run.

## Thermal balance diagnostics — experimental

The pure Python thermal balance engine compares aligned five-minute room samples over at least 24 hours, with a provisional minimum common coverage of 90% and ±0.3°C tolerance. It separates common temperature error from individual room residuals, uses area weighting only when every room has a valid area, and reports observed in-tolerance sample fractions. It returns settling when a known adjustment occurs within the analysis interval and monitor-only when the caller identifies an incompatible operating mode. These are descriptive diagnostics, not automatic hardware instructions or certification of balance. The zone topology adapter, conservative configuration epoch, journal-linked settling and preliminary panel display are implemented in source. Actual operating-mode verification, environmental comparability and detection of unlogged interventions remain pending.

Seven thermal balance unit tests were executed locally on 2026-11-27 and passed. The tested source and test file Git blob hashes were verified against the repository: `cb175b075f165a64f0626a46243e6ddaa8d6d79c` and `af6fea7901442319d6aad4fb69e2e3a039cd98d9`. No full Home Assistant runtime validation has been performed in this step.

## Consecutive stability and manual reference profiles — experimental

Stability evaluates consecutive rolling 24-hour windows, using five-minute aligned room samples. The pure motor accepts 3–7 days, defaults to five, and applies provisional criteria: 90% common sample coverage per window and 95% of observed common samples within ±0.3°C of each room's target. A failed daily window interrupts the consecutive count. Changes in configuration and logged before/after adjustments restrict the eligible window. The panel displays observed stability, not certified hydraulic balance. The actual operating regime, outdoor conditions, unlogged disturbances and sensor precision have not been validated; no automatic balance confirmation or equipment control is performed. The duration is configurable in the pure motor but not yet exposed in the UI.

Manual reference profile construction requires a complete set of circuit readings for each manifold in the selected hydraulic zone. Profiles retain source snapshot IDs, timestamps, targets, mode and flows, without automatically asserting balance or sending restoration commands. Persistent profile storage, UI, comparison and guided manual restoration remain pending. Snapshots may be from different times; the profile is a historical reference, not proof of simultaneous hydraulic conditions.

On 2026-11-27, 14 local unit tests passed in Python: nine stability and five profile construction tests. Tested Git blob hashes match the committed files: stability.py `83d762f8491f82f4b2a0c3e63693a73be54ff1b8`, test_stability.py `ce236e5c84aaf1f7cb7e27b0d03538d7c7e46b6d`, profiles.py `80d5a40e23949a077383e0286084a3d11f24e507`, test_profiles.py `3ec8e52c9596f13902a8cefa5e5a9f339bfb8518`. These results do not constitute a complete regression run or an HA integration test.

## Climate curve diagnostics — experimental

The pure Python heating-curve module evaluates reviewed comparable daily observations with aligned outdoor temperature and common room error, rejecting incomplete coverage and excessive local residuals. Provisional requirements: at least three distinct reviewed days for offset or fixed-supply hypotheses; at least five and a 5°C outdoor span for slope hypotheses; fixed supply observations require a maximum 2°C outdoor span. These are heuristics, not validated causal or automatic adjustment rules. Cooling slope diagnostics are not implemented. The comfort-direction helper preserves the distinction between desired room temperature and supply temperature, and blocks colder cooling targets pending condensation review.

On 2026-11-27, nine climate-curve unit tests were executed locally and passed. The exact tested Git blobs are climate_curve.py `5c05fe88529c9f32dec5a0a3226ab1950fee53c6` and test_climate_curve.py `661d66972f19e140cb2049fcf0ef759d79c8e856`. Actual outdoor sensor configuration, synchronized collection, comparable-day review UI, journal integration, comfort target editing and HA runtime testing remain pending. No equipment commands are issued.

## Principii / Principles

- Local, read-only towards physical equipment; manual adjustments by the user.
- Manufacturer-independent, with optional sensor inputs and user-defined names.
- The initial topology model supports multiple floors, manifolds and independent hydraulic zones.
- Full balancing method: continuous weather compensation with open circuits; fixed supply with continuous operation has limited support; ON/OFF-controlled systems remain monitoring-only.
- No mandatory YAML, no hardcoded personal configuration, no cloud subscription.

## Instalare / Installation — planned

Home Assistant 2026.11+ includes Marketplace under **Settings → Marketplace**, replacing standalone HACS. The project retains the required `hacs.json` metadata for Marketplace and legacy HACS compatibility.

[![Open in Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=mirel2505&repository=irpat-efficiency&category=integration)

[![Configure irPaT & Eficiență in Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=irpat_efficiency)

**Not ready for installation:** the repository is private during development and no validated release is available. These links are prepared for the future release. After publication, open the first link, confirm installation in your own Home Assistant, then use the second link to start setup. Restart only if Home Assistant requires it.

For older Home Assistant versions using HACS, compatibility remains a validation target, not a guarantee.

Official guide: https://contributors.home-assistant.io/marketplace/guides/integrations/

## Documentation

- [SPECIFICATION.md](SPECIFICATION.md) — agreed product requirements (Romanian)
- [ARCHITECTURE.md](ARCHITECTURE.md) — proposed architecture
- [ALGORITHMS.md](ALGORITHMS.md) — mathematical and validation contract
- [ROADMAP.md](ROADMAP.md) — development milestones

## Development

Run the initial pure-Python calculation, topology, temperature, history and hydraulic journal unit tests from the repository root:

```sh
python -m unittest discover -s tests -v
```

Home Assistant integration tests, browser rendering tests and Marketplace packaging validation remain pending.

## Support / Susținere

Donațiile sunt voluntare și susțin timpul investit în dezvoltare, mentenanța și costurile instrumentelor și abonamentelor AI folosite în proiect. Funcționalitățile integrării nu sunt condiționate de donații.

Voluntary donations support development time, maintenance and AI tool subscription costs. No features are paywalled.

[Buy Me a Coffee](https://buymeacoffee.com/rmirel2505o)

## License

GNU General Public License v3.0. See [LICENSE](LICENSE).
