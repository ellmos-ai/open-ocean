# Changelog

*[Deutsch](CHANGELOG_de.md)*

## Unreleased — 2026-08-29

### Added

- Root `ocean.py` lifecycle with `plan`, `up`, `status`, `down`, and `user add`.
- Capability-driven selection of exactly one resolved `runtime.host`.
- Local authenticated runtime supervisor and compatibility projections for the selected host.
- Password-safe delegated user bootstrap; passwords are not process arguments.
- Resolved component metadata in transaction reports for lifecycle consumers.
- Exact, content-hashed Full Dev component bindings for recipe-to-provider integrations; the first
  binding maps `module:software-endpoint-registry` to `system-explorer` at commit
  `ec50c92319ba8fc262d695b86818fc85666feff7`.
- Provider verification across repository origin, exact Git HEAD, clean worktree, module-manifest
  identity and declared capability before a bound component can become resolved.

### Fixed

- Disabled the runtime host's reload process and generated a per-start local secret so an
  authenticated stop cannot leave a reload child behind.
- Ignored stale stopped state from a previous instance during restart.
- Forced UTF-8 on the root CLI output streams so German help text keeps real umlauts on Windows.
- Prevented runtime imports from writing Python bytecode into external module projections.
- Preserved existing rollback-ledger entries across later component cycles; malformed, duplicate
  or conflicting entries now stop the transaction before writes.

### Verified

- 126 tests pass, including real HTTP start/status/user/stop/restart acceptance.
- A live private Full Dev sandbox verified 29 bundle pins, resolved 52 modules and 62 skills, and
  reached a healthy web login surface on `127.0.0.1`.
- The real `software-endpoint-registry` provider was fetched at its exact pin, projected two
  software endpoints (CLI and HTTP), and added one rollback-ledger entry without losing the 62
  existing skill entries.
- The real private runtime created a random disposable administrator, verified its password hash,
  and returned to the original zero-user state after cleanup.
- Twenty-five module references remain unresolved; nine are required, so the run still reports
  `full_composition: false`.
- After OneDrive resumed, the live Full Dev authority advanced from 29 to 30 bundle refs. A fresh
  read-only plan stopped fail-closed on three recipe-pin mismatches; no new apply replaced the
  healthy installed snapshot.

No release, tag, visibility change, or `PRIVATE.txt` change is part of this entry.
