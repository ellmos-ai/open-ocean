# Changelog

*[Deutsch](CHANGELOG_de.md)*

## Unreleased — 2026-08-29

### Added

- Root `ocean.py` lifecycle with `plan`, `up`, `start`, `status`, `down`, and `user add`.
- Capability-driven selection of exactly one resolved `runtime.host`.
- Local authenticated runtime supervisor and compatibility projections for the selected host.
- Password-safe delegated user bootstrap; passwords are not process arguments.
- Resolved component metadata in transaction reports for lifecycle consumers.
- Exact, content-hashed Full Dev component bindings for recipe-to-provider integrations; the first
  binding maps `module:software-endpoint-registry` to `system-explorer` at commit
  `ec50c92319ba8fc262d695b86818fc85666feff7`.
- Provider verification across repository origin, exact Git HEAD, clean worktree, module-manifest
  identity and declared capability before a bound component can become resolved.
- Capability-selected OCEAN operator entry: a resolved `unified-gui.host` is mounted at
  `/control/`, receives the deployment title `OCEAN Full Dev`, and runs on dedicated default port
  `8810` rather than the runtime provider's standalone TerminPilot PWA origin.

### Fixed

- Disabled the runtime host's reload process and generated a per-start local secret so an
  authenticated stop cannot leave a reload child behind.
- Ignored stale stopped state from a previous instance during restart.
- Recovered an installed snapshot from a stale `running` state after its supervisor and child had
  disappeared, without reapplying changed live recipe authority; occupied old or requested ports
  still fail closed.
- Replaced the incorrect provider-root product URL with the resolved OCEAN operator surface. The
  former HTTP-200 check had accepted TerminPilot's domain UI without verifying product identity.
- Forced UTF-8 on the root CLI output streams so German help text keeps real umlauts on Windows.
- Prevented runtime imports from writing Python bytecode into external module projections.
- Preserved existing rollback-ledger entries across later component cycles; malformed, duplicate
  or conflicting entries now stop the transaction before writes.

### Verified

- 128 tests pass, including real HTTP start/status/user/stop/restart, stale-state recovery and
  product-surface selection acceptance.
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
- The installed snapshot was restarted at `http://127.0.0.1:8810/control/`. HTTP and a real
  Playwright browser showed `OCEAN Full Dev`, no TerminPilot/appointment-coordination markers, and
  a navigable Skills panel; port `8800` was no longer listening.

No release, tag, visibility change, or `PRIVATE.txt` change is part of this entry.
