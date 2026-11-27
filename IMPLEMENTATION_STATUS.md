# Implementation status and release gates

2026-11-27. This document describes the implemented development build, not a certified installation or a complete implementation of SPECIFICATION.md. The earlier percentages in ROADMAP.md are subjective estimates for the initial usable build, not measured percentages of the full specification or test completion.

## Scope of Beta 1

| Area | Implemented in source | Not yet delivered or verified |
| --- | --- | --- |
| Configuration | Native options flow, topology, entity selectors, stable identity edits, explicit non-cascading removal | Dedicated graphical wizard, structural reassignments, temporary suspension, full config import, physical floor plans, detailed construction properties |
| Sensor quality | Units, missing and stale values, temperature sensor identity validation | User-calibrated offsets, primary/backup aggregation, configurable uncertainty and tolerances |
| Room history | 5-minute local samples retained 8 days; 24/48/72/168 h and yesterday comparison, zone aggregation | Recorder import, 30/365-day summaries, arbitrary history charts, long-term temperature retention |
| Hydraulics | Manual journal, profiles, raw flow comparison, pure normalization algorithm, physical circuit order | Full journal pagination, complete normalization review workflow, guided adjustment/keep/revert, hardware limits and position metadata |
| Thermal review | Zone residuals/common error, consecutive observed stability, manually reviewed curve and natural cooling | Adjustable stability criteria, persistent reviewed curve/inertia reports, automatic disturbance qualification; no certified balance |
| Energy | Source telemetry, explicit fluid properties, electrical ledger, matched subset ratios, current tariff, observed defrost duration/electricity and tur drop | Fuel measurement workflow, verified whole-period COP incl. all modes, per-area metrics in panel, defrost thermal energy and recovery, advanced hybrid attribution |
| Building | Reviewed retained-period net heat observation and before/after report | Complete building envelope model and intervention journal |
| Cooling | Dew point, surface and water proxy review, separate targets/profiles | Configurable margin and optional notifications; hardware safety remains external |
| UX | Native bilingual forms, simple/expert panel, HA theme, manual manifold readings, responsive CSS | Visual floor plan, demo mode, complete accessibility and end-to-end HA browser verification (isolated Chromium tests passed) |
| Data | Local HA Store, analysis CSV/JSON, native backup preparation | Full HAOS restore/restart validation (native Core archive recovery passed), per-integration import, migration fixtures and redacted diagnostic export |
| Packaging | Manifest, hacs.json, workflows, README, GPLv3 | Real installation validation and catalog submission |

The beta scope is intentionally advisory-only. No automatic equipment control, no remote telemetry, no paywalled features. The above gaps are retained in the full specification; they are not silently declared complete.

## Release gates

1. Review remaining product scope and explicitly distinguish initial beta from future features. Keep experimental warnings.
2. Validate package contents, manifest, translation files, asset loading and supported HA versions.
3. Run full unit regression and JS contract/behavior checks on the exact same commit. Capture logs and commit identity; never substitute earlier local subsets for a full checkout.
4. Run isolated Home Assistant setup/options/reload/unload, authenticated admin/non-admin API calls, native backup and restore, and desktop/mobile panel interaction. Check no unintended physical device or HA service calls.
5. Confirm data retention and resource use, stale or missing readings, restart, counter resets, DST, measurement-boundary changes and preservation of existing IDs and history.
6. Obtain owner approval for beta install on the owner's Home Assistant. Verify live readings and manual workflows. Avoid repeated production restarts.
7. Obtain separate approval before any public release, public repository change or catalog submission.

Verified baseline: commit 107917792cdccb3e0ffcd843385ed97a21050073 passed all three workflows (306 Python, 17 static contracts, 7 JS class checks, 7 real Core scenarios per supported version, 2 Chromium scenarios, package validation). Core archive recovery is not a complete HAOS recovery. Chromium used synthetic WebSocket responses. Owner installation has not been attempted. See ROADMAP.md for evidence and limitations.
