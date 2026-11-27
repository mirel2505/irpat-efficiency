# irPaT & Eficiență

**Asistență locală pentru echilibrarea hidraulică și termică a încălzirii și răcirii prin pardoseală cu agent termic.**

Local, advisory-only Home Assistant integration for hydronic radiant floor heating and cooling.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support%20development-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/rmirel2505o)

## Stadiu / Status

**0.1.0.dev0 — private beta candidate, not a public release.** The tested baseline passed isolated Core, Chromium and archive recovery checks. Installation on the owner's Home Assistant requires explicit approval. See [implementation scope and release gates](IMPLEMENTATION_STATUS.md) for the distinction between implemented functionality and the full product specification.

## Funcționalități / Implemented in source

- Configurare nativă HA, fără YAML obligatoriu: niveluri, camere, zone hidraulice, distribuitoare, circuite, surse și senzori. Editare cu identificatori stabili și eliminare confirmată fără ștergerea în cascadă. / Native configuration and safe identity-preserving editing.
- Panou local în sidebar, administrator-only, română/engleză, mod simplu/expert, teme HA, afișare adaptivă. / Local bilingual panel with simple and expert views.
- Monitorizare instantanee a temperaturilor și țintelor de încălzire/răcire; statistici 24/48/72/168 h și comparație cu ieri la aceeași oră. Istoricul local păstrează 8 zile; golurile rămân vizibile. / Room temperature monitoring and bounded local history.
- Jurnal manual de debite, observații înainte/după, profiluri și comparații brute pe circuit. Ultima observație afișată nu reprezintă debit live. / Manual hydraulic observations and reference profiles.
- Diagnostic termic pe zone, abatere comună și diferențe între camere, stabilitate observată, analiză climatică și răcire naturală cu confirmarea condițiilor de către utilizator. / Thermal balance, reviewed climate and natural cooling observations.
- Puteri, diferență tur-retur, energie electrică, cost orientativ și raport energetic pe intervalele cu măsurători compatibile; jurnale de degivrare și regim. / Energy monitoring with measurement boundaries and coverage.
- Punct de rouă și indicator de risc de condens, cu distincția dintre temperatura măsurată a suprafeței și temperatura apei. / Condensation review; independent physical protection remains necessary.
- Rapoarte comparative ale clădirii, export JSON versionat și opt categorii CSV; pregătirea jurnalelor pentru backupul nativ HA. / Reviewed building reports, data export and native backup preparation.

No external AI or telemetry service is required. No service calls to physical heating/cooling equipment. A selected display mode does not change the equipment mode. Advice remains conditional on measurement coverage, accuracy, comparability and configured operating assumptions.

## Configurare / Planned first setup

After a validated installation, add the integration from Settings → Devices & services. Create a named installation, then open Configure and add floors and hydraulic zones before rooms, sources, manifolds, circuits and bindings. Select sensors using the native entity selectors; thermostats supply current_temperature, not setpoints. Set heating and cooling targets separately. Save configuration explicitly. Open the irPaT & Eficiență sidebar panel.

Select Expert to see profiles, reviewed climate and inertia forms, mode/defrost journals, building reports and export. Record physical flow readings manually. Leave unavailable values empty. Do not confirm measurement boundaries, continuous operation or comparable conditions without evidence.

Temperature history samples every five minutes while HA is running; reports older than the provisional two-hour limit and future timestamps are excluded. Configuration edits restart eligible comparison history conservatively. A retained sample is not proof of a fresh physical sensor measurement. Do not interpret stability as certified hydraulic balance.

## Backup and recovery / Backup și restaurare

Use **Settings → System → Backups** and include Home Assistant settings. Keep the backup and emergency kit outside the HA device. The integration retries pending defrost/mode journal saves before native backup. This is not an atomic snapshot across all stores; unsaved records may be lost. Restoring HA settings may replace other system configuration. Keep a current backup before restoring. CSV/JSON are analysis archives, not directly restorable backups. See [official HA backup guidance](https://www.home-assistant.io/common-tasks/general/backups/).

## Instalare / Installation — not released

Planned distribution targets are Home Assistant Marketplace and compatible HACS installations. Metadata and links are prepared; distribution through these catalogs is not yet validated and the repository is private. The private GitHub Actions candidate contains the tracked integration folder, documentation and a SHA-256 checksum. It is not a public release.

[![Open in Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=mirel2505&repository=irpat-efficiency&category=integration)

[![Configure irPaT & Eficiență in Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=irpat_efficiency)

Release and catalog availability require owner approval and validation. See the [Marketplace integration guide](https://contributors.home-assistant.io/marketplace/guides/integrations/).

## Development and verification

Run from the repository root:

```sh
python -m unittest discover -s tests -v
python -m compileall -q custom_components
node --check custom_components/irpat_efficiency/frontend/panel.js
node scripts/check_ui_contracts.mjs
node scripts/test_panel_behavior.mjs
```

Verified baseline commit [1079177](https://github.com/mirel2505/irpat-efficiency/commit/107917792cdccb3e0ffcd843385ed97a21050073), 2026-11-27: 306 Python tests, 17 static contracts, 7 JavaScript class tests, 7 real Core tests on each of 2026.10.4 and 2026.11.2, 2 Chromium scenarios with synthetic HA responses, and package validation. Native encrypted and unencrypted archive recovery passed on synthetic files in isolated directories; this is not an HAOS restart/restore test. Full integrated browser session and real installation validation remain open. See the Actions runs and ROADMAP.md. No public release.

- [SPECIFICATION.md](SPECIFICATION.md) — original full product requirements
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) — current scope, gaps, release gates
- [ARCHITECTURE.md](ARCHITECTURE.md) — architecture
- [ALGORITHMS.md](ALGORITHMS.md) — algorithms
- [ROADMAP.md](ROADMAP.md) — chronological development and verification record

## Susținere / Support

Donațiile sunt voluntare și susțin timpul investit în dezvoltare, mentenanța și costurile instrumentelor și abonamentelor AI folosite în proiect. Funcționalitățile integrării nu sunt condiționate de donații.

Voluntary donations support development, maintenance and AI tool subscription costs. No features are paywalled.

[Buy Me a Coffee](https://buymeacoffee.com/rmirel2505o)

## License

GNU General Public License v3.0. See [LICENSE](LICENSE).
