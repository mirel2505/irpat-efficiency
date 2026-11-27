# Roadmap
All versions are targets, not release promises.
- 0.1.0: repository, specification, license, funding, integration skeleton, manifest, config entry lifecycle, pure calculation tests; HACS package validation and HA smoke test before declaring installable.
- 0.2.0: graphical onboarding and sensor selectors, aliases, reconfiguration.
- 0.3.0: floors, zones, sources, rooms, manifolds, ordered loops, graphical editor.
- 0.4.0: state subscriptions, validation, historical aggregation, comparison.
- 0.5.0: hydraulic snapshots/journal, normalization, profiles and graphical manifold.
- 0.6.0: room balance, evidence-based advice, settling and confirmation.
- 0.7.0: weather compensation and general comfort adjustment, mode eligibility.
- 0.8.0: thermal inertia, building and source efficiency, multiple source boundaries.
- 0.9.0: cooling/dew point, reports, export/restore, notifications, accessibility and diagnostics.
- 1.0.0: integration, migration, safety and real-world beta validation; documentation, public release and HACS catalog submission if eligible.
Release gates: tests, no equipment writes, no user-specific defaults, missing-data scenarios, read-only hardware, graphical configuration, no loss of history, local operation. Private repository during initial development; public release needs owner approval.

## Distribution update — 2026-11-27
Home Assistant Marketplace (built into Home Assistant 2026.11 and newer) is the primary installation and update target, replacing standalone HACS. Keep `hacs.json` and the compatible repository layout; the legacy HACS validation action and catalog remain relevant. Older HACS compatibility is subject to testing. README must provide My Home Assistant links for opening the Marketplace repository (`marketplace_repository`) and starting setup after installation (`config_flow_start`). Public availability requires owner approval, a public repository and a validated package; default catalog listing is a separate step. Follow https://contributors.home-assistant.io/marketplace/guides/integrations/ and https://contributors.home-assistant.io/marketplace/how-it-works/ for publication requirements. Ship custom brand images in the integration's `brand/` folder and validate translations and manifest before release. This update supersedes earlier references to HACS as the primary installer.


## Audit gate — 2026-11-27
Pause new features at approximately 85% estimated implementation, not validation.
Current audit: temperature sensor independence and paired-energy measurement identity corrections committed. Room history now stages samples before saving and filters comparisons by the committed configuration epoch. Six new persistence tests passed locally in Python 3.13.5; the available local subset ran 79 tests successfully, but it is not a verified complete checkout of the latest repository. Do not treat previously reported totals as verified whole-repository CI results.
Next: audit defrost and mode journal persistence, failure recovery, shared-meter attribution and configuration changes; audit entry setup/unload/reload and frontend/backend contracts; run a complete regression from one pinned commit and actual Home Assistant compatibility tests. Simulated disk errors and restart tests are not physical power-loss tests.
Remaining implementation after audit: CSV/JSON export, backup/restore, frontend completion, documentation, package and beta validation. Keep repository private; do not modify live equipment or publish without explicit owner approval.


### Audit continuation — persistence, lifecycle and frontend contracts
- Event journals: persist before publishing; bounded pending queue; retry on normal stop; report pending count and save failure. Defrost attribution excludes shared electricity meters and stale readings (provisional 60 s).
- Entry lifecycle: all seven components are rolled back on partial initialization failure; duplicate initialization blocked; unload attempts every component and retains failed resources for retry.
- Room readings: stale reports (over 7200 s) and future timestamps rejected before preview/history; frontend labels invalid timestamps and partial readings.
- Verification: 98 tests passed in the available Python 3.13.5 subset, including 19 new tests (6 journal, 4 monitor adapter, 4 lifecycle, 5 temperature adapter). The new adapter/lifecycle tests use simulated Home Assistant services and stores. Four lifecycle and three temperature adapter test cases reproduced failures before correction. Hashes of new tested source files match committed copies. Five frontend WebSocket commands match the five registered backend endpoints by static inspection; browser execution and real HA API compatibility remain unverified.
- Resume audit with actual HA compatibility and full pinned-commit regression; check all WebSocket payload schemas, translations, remaining frontend rendering and real restart/unload behavior. Actual physical power-loss durability remains untested. No new feature development until the audit gate is satisfied. Remaining work remains CSV/JSON export, backup/restore, frontend completion, documentation, packaging and beta validation. Implementation estimate remains 85%.


### Export implementation — 2026-11-27
Implemented administrator-only on-demand JSON archive (version 1, committed records plus storage warnings, explicitly not a restore format) and eight CSV categories. CSV preserves measurement segments and marks matched energy as a subset, escapes formula-like text, uses UTF-8 BOM, and excludes unsaved events. Individual file size limit is 4 MiB; oversized exports fail explicitly, without truncating or changing data. Browser uses local Blob downloads and revokes object URLs.
Verification: 9 new export unit tests passed on Python 3.13.5; exact blob hashes verified for module and tests. A recovered earlier 216-test local subset plus the 9 new tests passed 225/225; it is not a current complete checkout. All 17 static UI contracts passed on pinned commit 4203eadcf9d26dbb57617186dd7c48ca8ab86f4b, JavaScript compiled without execution, and all eight CSV choices matched the backend. Added real-Core smoke-test cases for export; execution in HA and browser download still unverified.
Next: backup and safe recovery using Home Assistant's native backup capability where appropriate; avoid treating analysis archives as directly restorable or replacing multiple stores without a validated transaction. Complete UI, docs, packaging, full pinned-commit regression and isolated HA testing before installing on the owner's HA. Estimate 88% implemented, not validation. No live HA changes or publication.
