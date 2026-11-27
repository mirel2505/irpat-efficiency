# Changelog

## 0.1.0-beta.1 — First public beta

**THERMELYVO — Smart Heating & Cooling Analytics**

*Simplicity. Balance. Efficiency.*

This is a pre-release for testing, feedback and validation, not a stable release.

### Included

- THERMELYVO branding and bilingual guided configuration, compact dashboard and expert mode.
- Room temperature targets, local history, thermal balance and manual circuit-flow adjustment records.
- Source-wide weather-curve gating: only after relative balance and a persistent common deviation, with a minimum 48-hour post-adjustment observation period and adequate data.
- Heat-source diagnostics, thermal/electrical energy analysis, energy costs and defrost monitoring where measurements are available.
- Cooling monitoring and condensation indicators, reviewed reports, JSON/CSV export and Home Assistant backup preparation.

### Upgrade

The internal integration domain remains `irpat_efficiency`. The intended upgrade path preserves configuration and storage identity. Back up Home Assistant first; restart if necessary after updating. Do not reset configuration solely for the rename.

### Limitations

- Advisory only: no equipment control.
- Cooling curve optimization is not supported; condensation protection remains independent.
- Manual review of operating conditions and adequate sensor data are required.
- No certified hydraulic balance, guaranteed savings, or production installation/restore certification.
- Compatibility testing targets Home Assistant Core 2026.10.4 and 2026.11.2; browser tests use mock responses.

Report issues through [GitHub Issues](https://github.com/mirel2505/irpat-efficiency/issues) with anonymized diagnostic details. No personal email or private sensor data is required.
