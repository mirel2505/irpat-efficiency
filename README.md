# irPaT & Eficiență

**Asistență pentru echilibrarea hidraulică și termică a încălzirii și răcirii prin pardoseală cu agent termic.**

Local, advisory-only Home Assistant integration for hydronic radiant floor heating/cooling, hydraulic and thermal balancing, weather compensation, and energy efficiency.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support%20development-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/rmirel2505o)

## Stadiu / Status

**0.1.0.dev0 — experimental foundation, not ready for installation on a production system.**
Initial configuration entry, topology model, native options forms for adding floors, zones, rooms, manifolds, circuits, sources and ambient temperature bindings, and calculation primitives are implemented in source. Native forms are not yet validated on Home Assistant. The dedicated graphical panel, complete configuration editing, data collection, historical data, balancing assistant and reports are not yet implemented. Marketplace metadata (hacs.json) is present; installation has not been validated. No release is available.

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

Run the initial pure-Python calculation and topology unit tests from the repository root:

```sh
python -m unittest discover -s tests -v
```

Home Assistant integration tests, frontend and Marketplace packaging validation remain pending.

## Support / Susținere

Donațiile sunt voluntare și susțin timpul investit în dezvoltare, mentenanța și costurile instrumentelor și abonamentelor AI folosite în proiect. Funcționalitățile integrării nu sunt condiționate de donații.

Voluntary donations support development time, maintenance and AI tool subscription costs. No features are paywalled.

[Buy Me a Coffee](https://buymeacoffee.com/rmirel2505o)

## License

GNU General Public License v3.0. See [LICENSE](LICENSE).
