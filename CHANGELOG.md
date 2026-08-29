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
- The second exact binding maps `module:automation-registry` to `automation-master` at commit
  `ad40de721615518e409b53b00ed4b2a49840db28` and requires `automation.registry`.
- Provider verification across repository origin, exact Git HEAD, clean worktree, module-manifest
  identity and declared capability before a bound component can become resolved.
- Capability-selected OCEAN operator entry: a resolved `unified-gui.host` is mounted at
  `/control/`, receives the deployment title `OCEAN Full Dev`, and runs on dedicated default port
  `8810` rather than the runtime provider's standalone TerminPilot PWA origin.
- OCEAN-owned origin adapter for Root redirect, product manifest/offline identity, legacy
  service-worker/cache eviction and provider API delegation.

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
- Moved the active-runtime and requested-port preflight ahead of the apply transaction. A second
  `up --apply` can no longer Fetch/Activate anything before reporting that the sandbox is running.
- Closed the remaining PWA identity leak on port `8810`: the provider had still exposed its own
  root, manifest and root-scoped worker on OCEAN's new origin, so port separation alone was not a
  complete product boundary.

### Verified

- 133 tests pass, including real HTTP start/status/user/stop/restart, stale-state recovery,
  product-surface/origin selection, PWA cleanup and pre-write active-runtime rejection.
- The current private Full Dev integration candidate verifies 30/30 bundle pins, resolves 53
  modules and 80 skills, and is healthy at `http://127.0.0.1:8810/control/`.
- The real `software-endpoint-registry` provider was fetched at its exact pin, projected two
  software endpoints (CLI and HTTP), and added one rollback-ledger entry without losing the 62
  existing skill entries.
- The real `automation-registry` provider is a clean detached checkout at the exact
  `automation-master` pin and origin; its module manifest declares `automation.registry`.
- The Therapy bundle adds 18 resolved and installed skills. The append-preserving ledger now holds
  80 skill entries and two bound-module entries.
- The real private runtime created a random disposable administrator, verified its password hash,
  and returned to the original zero-user state after cleanup.
- Twenty-four module references remain unresolved; eight are required, so the run still reports
  `full_composition: false`.
- The former three recipe-pin mismatches were reconciled without ad-hoc repinning on pushed branch
  `ellmos-development-system@489b67880b42ba4bd2a1d8052239896f84192269`; merging that branch into
  canonical recipe `main` remains separate work.
- The installed snapshot was restarted at `http://127.0.0.1:8810/control/`. HTTP and a real
  Playwright browser showed `OCEAN Full Dev`, no TerminPilot/appointment-coordination markers, and
  a navigable Skills panel; port `8800` was no longer listening.
- In a persistent Playwright profile, the seeded legacy provider cache was removed while an
  unrelated synthetic future-OCEAN cache remained; service-worker registrations were zero, `/`
  redirected to the OCEAN overview, and the UTF-8 title retained its em dash and German `Ü`
  without replacement characters.

An integration-checkpoint tag is not a public release. No visibility or `PRIVATE.txt` change is
part of this entry.
