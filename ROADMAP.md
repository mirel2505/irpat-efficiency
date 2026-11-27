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