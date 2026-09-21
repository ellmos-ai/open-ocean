# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

*[Deutsch](CHANGELOG_de.md)*

## Unreleased — 2026-09-09

### Added

- Added `ocean inspect`, a read-only adapter to the exact installed System Explorer pin. It
  verifies the OCEAN install/binding and provider identity, delegates resolution, Ed25519 receipt,
  trust and coverage semantics to native APIs in a temporary store, rejects mixed valid/invalid
  receipt sets atomically, and emits deterministic JSON after omitting only four documented
  Store-bookkeeping `created_at` positions.
- Added explicit `ocean inspect --root-only-resolution` transport for native subsystem omission.
  Subsystem resolutions remain rejected by default; successful results expose the provider's
  `projection_scope` and `subsystems_omitted` fields so coverage status retains its exact boundary.

- `ocean start <role>` forwards an authoritative module `roles[]` entry to the
  Unified GUI console start window. The existing `ocean start --workspace ...`
  runtime path is unchanged. Missing optional console code degrades visibly to
  task-master, COMA and the module starter; `--dry-run` starts no provider.

- Pinned the accounts-core projection publisher and sqlite-transit-sync verifier for Finance
  Assist, and added an OCEAN consumer that verifies a closed projection before selecting only its
  allowlisted account fields through immutable, read-only SQLite access.
- Added fail-closed tests for projection changes and newly appearing SQLite sidecars. No live data,
  transport activation, checkpoint persistence, rollout, or cutover is included.

### Fixed

- Aligned the public repository surface with its actual visibility: removed concrete development
  host identifiers from shipped documentation and fixtures, replaced instance paths with neutral
  placeholders, and removed stale claims that the repository itself is still a private build.
- Reclassified `architecture/INSTALLER-TARGET.md` from a pre-implementation placeholder to the
  implemented supported-path contract, while keeping additional host adapters, upgrades and BACH
  setup parity explicitly open; aligned both BACH roadmaps and READMEs with that boundary.
- Integrated the Full Ocean lifecycle branch with the independent Path A metadata/CI baseline;
  preserved both change histories while resolving the `CHANGELOG.md` and `llms.txt` add/add
  conflicts.
- Made both secret-bearing Windows writers fail closed when `icacls` cannot apply the owner-only
  ACL, and remove their temporary file on ACL or atomic-replace failure instead of leaving secret
  material behind.
- Retry only transient `PermissionError` state reads while the Windows supervisor atomically
  replaces its runtime state; malformed JSON and all other read failures still fail closed.

### Verified

- The integrated PR #2 tree passes 181 tests and 2 subtests on Windows; Ruff and `compileall` are
  clean.

## Unreleased — 2026-08-30

### Verified

- A second, independent fresh-install host, `<FRESH-HOST>`, reached the same result:
  input worktrees `open-ocean@243a703c` (tag `ocean-full-laptop-hafenlicht-20260829`) and
  `ellmos-development-system@1b461c9c`, both detached and clean; pre-install suite pytest
  137/137, unittest 125/125, ruff clean, `compileall` exit 0.
- The plan before apply reported 28/28 bundles, 80/80 skills, but only 51/65 modules
  (`full_composition: false`) — three required providers not yet local. Apply fetched
  `automation-registry@ad40de721615518e409b53b00ed4b2a49840db28` and
  `automation-runtime@c2de7188626510b181c4ecf2708c15f2395e32aa` (both from
  `dev-bricks/automation-master.git`) and
  `software-endpoint-registry@ec50c92319ba8fc262d695b86818fc85666feff7` (from
  `ellmos-ai/system-explorer`) as clean detached checkouts.
- After apply: 28/28 bundles, 54/65 modules, 80/80 skills, no missing required component,
  `full_composition: true`, at `http://127.0.0.1:8810/control/`.
- A full `down`/`start` lifecycle cycle passed (stopped, port freed, no stale processes, then
  running again with no state reuse), followed by the same HTTP/browser/process identity checks.
- The hidden limited-user logon task `EllmosOceanFullUserStart` demand-started the pinned
  checkout: `LastTaskResult 267009` (`SCHED_S_TASK_RUNNING` — the expected code for an
  intentionally still-running server process, not `0`), one supervisor (PID 6460) and one child
  (PID 37676) under `pythonw.exe`, the child the sole listener on `8810`; `full_composition: true`
  held afterward. No physical reboot was tested.
- No BACH session sidecar was running on this host (`service.running: false`, `pid: null`), so
  none was stopped; BACH code, databases, tasks and configuration are unchanged.
- No user was created on this host — a deliberate decision (device-bound OS-account coupling
  instead of an additional app password), not an installation gap.

## Unreleased — 2026-08-29

### Added

- Paired English/German product-stack boundary documents for OPEN OCEAN, PRIVATE OCEAN,
  FULL OCEAN and the independent SPEEDBOAT sibling stack, backed by documentation-contract tests.
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
- The third exact binding maps the distinct logical `module:automation-runtime` role to its own
  `automation-master` placement at commit `c2de7188626510b181c4ecf2708c15f2395e32aa` and requires
  runtime observation, immutable receipts, and bounded statistics.
- Provider verification across repository origin, exact Git HEAD, clean worktree, module-manifest
  identity and declared capability before a bound component can become resolved.
- Capability-selected OCEAN operator entry: a resolved `unified-gui.host` is mounted at
  `/control/`, receives the deployment title `OCEAN Full Dev`, and runs on dedicated default port
  `8810` rather than the runtime provider's standalone TerminPilot PWA origin.
- OCEAN-owned origin adapter for Root redirect, product manifest/offline identity, legacy
  service-worker/cache eviction and provider API delegation.

### Fixed

- Removed the obsolete `ocean-full / open-ocean` equivalence from current product wording and
  marked it as superseded in the living plan: OPEN OCEAN is public, PRIVATE OCEAN is private and
  non-proprietary, and FULL OCEAN is their exact union.
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
- Retried transient Windows contention while atomically replacing the supervisor state file. A
  successful stop now leaves `stopped`, no temporary state file, no process and no listener.

### Verified

- 137 tests pass, including real HTTP start/status/user/stop/restart, stale-state recovery,
  product-surface/origin selection, PWA cleanup and pre-write active-runtime rejection.
- The current private Full Dev integration candidate verifies 28/28 OCEAN-family bundle pins,
  resolves 54 of 65 module references and all 80 skills, and is healthy at
  `http://127.0.0.1:8810/control/`.
- The real `software-endpoint-registry` provider was fetched at its exact pin, projected two
  software endpoints (CLI and HTTP), and added one rollback-ledger entry without losing the 62
  existing skill entries.
- The real `automation-registry` provider is a clean detached checkout at the exact
  `automation-master` pin and origin; its module manifest declares `automation.registry`.
- The real `automation-runtime` provider is a separate clean detached placement at the exact
  `automation-master` pin and origin. Installed-provider acceptance proved native provider and
  scheduler readback, an immutable content-hashed receipt, bounded statistics, and non-export of
  raw provider/scheduler content.
- The Therapy bundle adds 18 resolved and installed skills. The append-preserving ledger now holds
  80 skill entries and three bound-module entries.
- The real private runtime created a random disposable administrator, verified its password hash,
  and returned to the original zero-user state after cleanup.
- Eleven optional module references remain unresolved. No required component is missing, so the
  applied 28-bundle development composition reports `full_composition: true`. This is not a
  public-release, BACH-parity, or foreign-host full-system claim.
- Full Ocean selection commit `1b461c9cb900ada15b8e104f2586a6b4a1ea5278` is adopted in canonical
  recipe `main`; post-adoption readback is `b13f1b11626141d6dc6927028dc10008bc406866`.
- A fresh local Blue-Green apply into `C:\_Local_DEV\ocean-full` preserved the prior workspace as
  rollback, fetched all three exact provider pins, reached `full_composition: true`, and passed a
  real stop/start/stop/start cycle after the Windows state-file regression was fixed.
- A controlled stop/apply/start readback retained healthy OCEAN identity: Root returns `307` to
  `/control/`, the UTF-8 manifest names `OCEAN Full Dev`, and no TerminPilot product marker appears.
- The installed snapshot was restarted at `http://127.0.0.1:8810/control/`. HTTP and a real
  Playwright browser showed `OCEAN Full Dev`, no TerminPilot/appointment-coordination markers, and
  a navigable Skills panel; port `8800` was no longer listening.
- In a persistent Playwright profile, the seeded legacy provider cache was removed while an
  unrelated synthetic future-OCEAN cache remained; service-worker registrations were zero, `/`
  redirected to the OCEAN overview, and the UTF-8 title retained its em dash and German `Ü`
  without replacement characters.
- The hidden limited-user `EllmosOceanFullUserStart` logon task demand-started the pinned runtime
  checkout with task result `0`, exactly one supervisor/child/listener tuple and healthy Full Ocean
  status. `StartWhenAvailable` is deliberately off so registration cannot race a manual proof.
  This verifies the task path, not a physical reboot.
- BACH's former session sidecar stopped cleanly through its native CLI after OCEAN and its logon
  task were accepted. The operational task-race lesson is persisted as USMC lesson `62`.

An integration-checkpoint tag is not a public release. No visibility or `PRIVATE.txt` change is
part of this entry.

## [0.1.2] - 2026-09-12

### Changed
- **CI Matrix & Workflow Hardening**: Added pip caching (`cache: 'pip'`) to `actions/setup-python@v5` and configured `timeout-minutes: 15` runaway protection on test jobs in `.github/workflows/ci.yml`.
- **Automated Lifecycle Workflows**: Deployed standard ecosystem stale issue & PR workflow in `.github/workflows/stale.yml`.
- **Packaging & Test Dependencies**: Added `[project.optional-dependencies]` with test dependencies (`pytest`, `ruff`) in `pyproject.toml` and bumped version to `0.1.2`.
- **Multi-Host Gitignore Defense**: Hardened `.gitignore` against multi-host sync conflicts (`*-WORKSTATION*`, `*-ASUS-*`, `* (kopie)*`, `* (copy)*`, `*-conflict-*`, `*.sync-temp-*`), multi-agent locks (`LOCK`, `LOCK.*`, `*.lock`, `LOCK.permissions.json`), and wheel packaging artifacts (`wheelhouse/`, `.wheel-smoke/`).
- **Publication Gate Status Alignment**: Documented formal lifting of publication gate `PRIVATE.txt` per decision D-20260909-003 and user directive across `README.md`, `README_de.md`, and `llms.txt`.
- **Contract & Metadata Tests**: Expanded `tests/test_metadata.py` with tests for stale workflow integrity, pip caching, optional test dependencies, and multi-host gitignore patterns; synchronized test suite counts (113 passed tests).

## [0.1.1] - 2026-09-09

### Added
- **Bilingual README Architecture & Discoverability**: Full structural and anchor parity across `README.md` and `README_de.md`, integrated 14-point Quick Navigation, modern Shields.io badges, and enriched documentation.
- **Dual-Mermaid Diagrams**: Interactive system architecture flowchart (`flowchart TD`) and end-to-end package resolution, verification, staging, and transactional rollback lifecycle diagram (`sequenceDiagram` with autonumbering) in both language editions.
- **Governance & Runtime Invariants Matrix**: 10 core architectural invariants (`INV-LOCAL-01` through `INV-SLA-10`) detailing offline guarantees, fail-closed verification, transactional rollbacks, sandboxed activations, non-elevation, and SLA bounds.
- **Sibling Ecosystem & Partner Repositories**: Cross-referencing 16+ partner repositories across `ellmos-ai`, `dev-bricks`, `file-bricks`, `doc-bricks`, `entertain-and-more`, and `open-bricks`.
- **Security Policy Hardening (`SECURITY.md`)**: Added `security@open-bricks.org` and a binding 5-business-day triage guarantee in both German and English sections.
- **Third-Party Licenses Inventory (`THIRD_PARTY_LICENSES.md`)**: Documented zero-external-runtime-dependencies invariant and permissive licensing of development tooling.
- **Local Marketing Log (`MARKETING-LOG.txt`)**: Documented discoverability status, SEO keywords, and post-sluice directory listings strategy.
- **Automated Contract Tests (`tests/test_metadata.py`)**: Expanded test suite verifying 14-point navigation anchors, Mermaid syntax, invariants completeness, and licenses.
- **LLM Context Synchronization (`llms.txt`)**: Bumped version to 0.1.1 and refreshed timestamp to 2026-09-09.

## [0.1.0] - 2026-09-08

### Added

- **GitHub Actions CI Workflow**: Multi-OS (`ubuntu-latest`, `windows-latest`, `macos-latest`) and multi-version Python matrix (`3.10`, `3.11`, `3.12`, `3.13`) in `.github/workflows/ci.yml` with concurrency control (`cancel-in-progress: true`), ruff linting, bytecode compilation check, and pytest execution.
- **PEP 621 Standard Packaging & Metadata (`pyproject.toml`)**: Standardized project metadata with classifiers (Python 3.10-3.13, OS Independent, Linux, Windows, macOS), pytest configuration (`pythonpath = ["."]`), ruff configuration, and complete ecosystem URLs (`Homepage`, `Repository`, `Issues`, `Changelog`, `Documentation`, `Security`, `Parent Organization`, `Umbrella Ecosystem`).
- **Bilingual Security Policy (`SECURITY.md`)**: Detailed security and privacy invariants covering Local-First & Zero-Egress, Fail-Closed Verification & Transactional Rollback, Mandatory Dry-Run-First Safety Gate, Sandboxed Activation Isolation, and Non-Elevation; includes supported versions table (`0.1.x`), 48-hour response SLA, and official security reporting channels.
- **Automated Metadata & Contract Test Suite (`tests/test_metadata.py`)**: 7 new contract tests validating CI workflow integrity, PEP 621 metadata declarations, bilingual security policy invariants, README badges & documentation parity, llms.txt context synchronization, `.gitignore` hygiene, and offline zero-egress invariants.
- **Machine-Readable Project Context (`llms.txt`)**: Overview of architecture, invariants, repository structure, and verified test suites.
- **Gitignore Hardening**: Enhanced `.gitignore` with synchronization conflict patterns (`*.sync-conflict-*`, `*.conflict`, `*-CONFLIT-*`), test/linter caches (`.ruff_cache/`, `.mypy_cache/`), and temporary backup files.
- **README Status & Shields.io Badges**: Integrated standard ecosystem badges for CI status, test suite passing count, Python versions, platforms, MIT license, Security Policy, Privacy, and ecosystem links in both `README.md` and `README_de.md`.
