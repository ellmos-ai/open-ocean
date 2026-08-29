# Changelog

*[Deutsch](CHANGELOG_de.md)*

## Unreleased — 2026-08-29

### Added

- Root `ocean.py` lifecycle with `plan`, `up`, `status`, `down`, and `user add`.
- Capability-driven selection of exactly one resolved `runtime.host`.
- Local authenticated runtime supervisor and compatibility projections for the selected host.
- Password-safe delegated user bootstrap; passwords are not process arguments.
- Resolved component metadata in transaction reports for lifecycle consumers.

### Fixed

- Disabled the runtime host's reload process and generated a per-start local secret so an
  authenticated stop cannot leave a reload child behind.
- Ignored stale stopped state from a previous instance during restart.
- Forced UTF-8 on the root CLI output streams so German help text keeps real umlauts on Windows.
- Prevented runtime imports from writing Python bytecode into external module projections.

### Verified

- 114 tests pass, including real HTTP start/status/user/stop/restart acceptance.
- A live private Full Dev sandbox verified 29 bundle pins, resolved 51 modules and 62 skills, and
  reached a healthy web login surface on `127.0.0.1`.
- The real private runtime created a random disposable administrator, verified its password hash,
  and returned to the original zero-user state after cleanup.
- Ten required modules remain unresolved; the run therefore reports `full_composition: false`.

No release, tag, visibility change, or `PRIVATE.txt` change is part of this entry.
