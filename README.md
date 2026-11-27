# irPaT & Eficiență

**Asistență pentru echilibrarea hidraulică și termică a încălzirii și răcirii prin pardoseală cu agent termic.**

Local, advisory-only Home Assistant integration for hydronic radiant floor heating/cooling, hydraulic and thermal balancing, weather compensation, and energy efficiency.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support%20development-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/rmirel2505o)

## Stadiu / Status

**0.1.0.dev0 — experimental foundation, not ready for installation on a production system.**
Initial configuration entry and calculation primitives are implemented. The dedicated panel, sensor selection, historical data, balancing assistant and reports are not yet implemented. HACS metadata is present; installation has not been validated. No release is available.

## Principii / Principles

- Local, read-only towards physical equipment; manual adjustments by the user.
- Manufacturer-independent, with optional sensor inputs and user-defined names.
- Multiple floors, manifolds and independent hydraulic zones are planned.
- Full balancing method: continuous weather compensation with open circuits; fixed supply with continuous operation has limited support; ON/OFF-controlled systems remain monitoring-only.
- No mandatory YAML, no hardcoded personal configuration, no cloud subscription.

## Documentation

- [SPECIFICATION.md](SPECIFICATION.md) — agreed product requirements (Romanian)
- [ARCHITECTURE.md](ARCHITECTURE.md) — proposed architecture
- [ALGORITHMS.md](ALGORITHMS.md) — mathematical and validation contract
- [ROADMAP.md](ROADMAP.md) — development milestones

## Development

Run the initial pure-Python unit tests from the repository root:

```sh
python -m unittest discover -s tests -v
```

Home Assistant integration tests, frontend and packaging validation remain pending.

## Support / Susținere

Donațiile sunt voluntare și susțin timpul investit în dezvoltare, mentenanța și costurile instrumentelor și abonamentelor AI folosite în proiect. Funcționalitățile integrării nu sunt condiționate de donații.

Voluntary donations support development time, maintenance and AI tool subscription costs. No features are paywalled.

[Buy Me a Coffee](https://buymeacoffee.com/rmirel2505o)

## License

GNU General Public License v3.0. See [LICENSE](LICENSE).
