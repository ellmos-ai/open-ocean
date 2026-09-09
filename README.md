<img src="assets/banner.png" width="100%" alt="open-ocean Banner">

# open-ocean

**Free the ocean.**

The free community system of the ellmos ecosystem.

*[Deutsch](README_de.md)*

> **Private build, and early on purpose.** This repository exists before the system does, so the
> architecture has somewhere to live while it is being decided. It opens when the water reaches
> the ocean — see *[Release conditions](#release-conditions)*.

---

## Read this first: this repository is a building site

**The released OPEN OCEAN system is not here yet.** The local FULL OCEAN development composition is now
runnable on the development host: it can plan, install, start, inspect, bootstrap a user, stop and
restart one declared `runtime.host`. This is the first usable OCEAN product slice, not a BACH-parity
or OPEN OCEAN release claim. The verified 28-bundle composition now resolves every declared required
component and truthfully reports `full_composition: true`; its eleven unresolved module references
are optional for this composition.

OCEAN consumes the recipes from their canonical repository instead of copying them here. The
transaction layer resolves, verifies, fetches, places, activates and rolls back; the lifecycle
layer operates the selected runtime in an explicit local sandbox. The current Full Dev host is the
private `ellmos-core`, selected by capability rather than hard-coded as the future OPEN OCEAN runtime.
When the resolved composition also provides `unified-gui.host`, OCEAN exposes that operator UI as
its product entry point. The current development URL is `http://127.0.0.1:8810/control/`; the
dedicated port keeps OCEAN separate from the runtime provider's standalone TerminPilot PWA origin.
An OCEAN-owned origin adapter also redirects `/` to that entry point, serves the OCEAN manifest and
offline identity, and evicts provider service workers/caches before they can claim the OCEAN URL.

| Repository | What it is | State |
|---|---|---|
| **bundles** | the recipe layer: manifests, catalogue, export tool | private, releasing wave by wave |
| **open-ocean** (here) | the system build: architecture, installer, the thing that consumes recipes | private, early |

## The name, and the architecture it carries

The ratified product boundary is documented in
[Product stack boundaries](architecture/PRODUCT-STACK-BOUNDARIES.md):

- **OPEN OCEAN = PUBLIC**
- **PRIVATE OCEAN = PRIVATE, NON-PROPRIETARY**
- **FULL OCEAN = OPEN OCEAN + PRIVATE OCEAN**
- **SPEEDBOAT = PROPRIETARY + explicitly selected OPEN-/PRIVATE-OCEAN parts**

This repository builds OPEN OCEAN and operates FULL OCEAN as the private development/test
composition. SPEEDBOAT is an independent sibling stack, not an OCEAN edition or overlay.

The ecosystem names its layers after water, because the metaphor carries the architecture rather
than decorating it:

| Term | What it is |
|---|---|
| **stream / water** | the process itself — data, work, results flowing through everything |
| **Bach / Rinnsal** | the wild, grown streams: the original personal full instance |
| **water pipes** | the same water, tamed and modularised — modules and bundles |
| **waterfall** | the declarative source: the kit, the recipes, the catalogues |
| **ocean** | the successor product family; the end of the line Bach → Rinnsal → ocean |
| **open-ocean** | the part that belongs to everyone: the free community system |
| **private-ocean** | private, non-proprietary OCEAN components |
| **full-ocean** | OPEN OCEAN + PRIVATE OCEAN; the complete OCEAN development/test composition |
| **speedboat** | an independent proprietary stack that selects shared OCEAN parts explicitly |

The governing rule is a conservation law: **extraction changes the bed, never the water.**
Restructuring must preserve function — "same volume of water" means functional parity. That is
not decoration either; it is the release bar this repository has to clear.

Most extraction has already happened. The current work makes legacy BACH more modular by replacing
its internals with the canonical modules and bundles while OCEAN is completed as its successor.
A valuable BACH-only component may still be extracted, but that is an exception with its own gate.
BACH stays supplied by consuming the same modules as OCEAN; any later move to LTS, freeze, or
archive remains an explicit product decision, never an automatic consequence of this plan.

## What is actually in here

```
architecture/
  open-ocean.skeleton.v1.json   which recipes the system intends to consume, pinned by hash
  ocean-full-dev.component-bindings.v1.json  exact, non-authoritative per-module integration pins
  ocean-full-dev.source-pins.v1.json  reviewed recipe, binding, crosswalk and Skills Registry pins
  INSTALLER-TARGET.md           what the installer has to become, and what it must not do
  OCEAN-DEV-BUILD-PLAN_2026-08-18.md  staged build plan and verified foreign-host integration evidence
  BACH-EXTRACTION-ROADMAP.md    extraction order, parity gates and Cluster 9 kernel map
  bach-parity-baseline.v1.json  machine-readable registry and Cluster 9 coverage baseline
  bach-k9-data-contract.v1.json pinned dbsync/snapshot operation and fixture contract
  bach-k9-dbsync-adapter.v1.json thin lifecycle-adapter specification
  session-checkpoint-capability.v1.json boundary of the correct snapshot carrier
tools/
  audit_bach_handlers.py        side-effect-free source audit against that baseline
  check_k9_data_contract.py     static BACH check plus two synthetic carrier fixtures
  resolve_bundles.py            Resolve+Verify: bundle refs -> flat, hash-checked component plan
  host_adapters.py              vendor-neutral Activate: read-only readiness check plus write-side
                                 activate_skill/rollback_activate_skill (Claude Code as reference)
  fetch_place.py                Fetch+Place for module: components, SHA-pinned, fail-closed (no
                                 silent default-branch fallback)
  ocean_dev.py                  single entry point: Resolve -> Verify -> Fetch/Place -> Activate for
                                 one ring or a complete system manifest; dry-run by default,
                                 --apply for real writes, --rollback
  source_pins.py                fail-closed source-provenance verification before Resolve/Fetch
  accounts_projection.py       verify/read the minimal account projection without state writes
  ocean_lifecycle.py            capability-driven plan/up/status/down/user lifecycle
  runtime_supervisor.py         authenticated loopback supervisor for one runtime instance
  runtime_user.py               password-safe user bootstrap delegated to the runtime
ocean.py                        user-facing OCEAN Full Dev CLI
PRIVATE.txt                     the publication gate, committed on purpose
```

The skeleton references 13 bundles in two rings — the functional core, and breadth around it. It
**references** them: no manifest is copied here. Copies would fork the moment the recipe
repository moves on, and would make this repository look further along than it is.

### Local composition modes

- The repository skeleton is the 13-bundle public scope; choose ring `1`, `2`, or `all`.
- OCEAN Full Dev consumes the existing external `ellmos.system.v1` full-system manifest and all 28
  of its OCEAN-family `bundle_refs[]`. Proprietary SPEEDBOAT bundles are excluded. The manifest and
  private recipes remain in their canonical stores; nothing is copied into this repository.

```text
python tools/ocean_dev.py --bundles-root <recipe-projection> \
  --system-manifest <ellmos-development-fullsystem/system.v1.json> \
  --source-pins architecture/ocean-full-dev.source-pins.v1.json
```

Without `--apply` this is a read-only dry-run. A system manifest cannot be combined with a numbered
ring; partial work is selected adaptively as a separate bundle cycle, not by silently truncating
the declared Full Dev composition.

The default `--component-bindings` overlay closes recipe-to-provider naming gaps without changing
the canonical recipe or module catalog. Each binding is exact and fail-closed: component ref,
repository, full commit SHA, placement, provider manifest ID and required capabilities must all
match and the checkout must be clean before OCEAN treats the provider as resolved. The shipped
overlay currently binds `module:software-endpoint-registry` to `system-explorer` and the distinct
logical roles `module:automation-registry` and `module:automation-runtime` to independently pinned
placements of `automation-master`.

The Finance Assist path also pins `accounts-core` as the sole publisher and
`sqlite-transit-sync` as the read-only contract verifier. OCEAN's bounded consumer is separate:

```text
python tools/accounts_projection.py --database <closed-accounts.sqlite> \
  --consumer-id ocean-accounts-consumer --minimum-offline-seconds 2592000 \
  --previous-checkpoint <last-seen-checkpoint>
```

It verifies first, rejects sidecars or a file that changes across verification/readback, opens
SQLite with `mode=ro&immutable=1`, and returns only the contract's six consumer fields. It does not
persist a checkpoint, schedule transport, activate a live path, or write either database.

`ocean.py plan` and `ocean.py up` also pass the shipped `--source-pins` contract by default. Before
Resolve — and therefore before Fetch, Place or Activate — OCEAN requires the recipe input to be the
clean root checkout of the exact pinned Git origin and commit. It then verifies the recipe's native
component-registry binding self-hash, the raw Skills Crosswalk SHA-256, and the caller-supplied
Skills Registry URI/SHA-256 against one content-hashed contract. Any mismatch is an error, never an
implicit re-pin. Installed-snapshot `start` remains independent of changed live recipe authority.

The product lifecycle is exposed at the repository root:

```text
python ocean.py plan <composition arguments>
python ocean.py up <composition arguments> --apply
python ocean.py start --workspace <local-sandbox>
python ocean.py status --workspace <local-sandbox>
python ocean.py user add --workspace <local-sandbox> --username <name> --email <address>
python ocean.py down --workspace <local-sandbox>
```

Run `python ocean.py --help` and the respective subcommand help for the complete arguments. User
passwords are prompted without echo and are never passed as process arguments; local automation
may use `--password-stdin`. `ocean up` uses the dedicated OCEAN port `8810` by default. `ocean
start` restarts the already installed, verified snapshot without consulting changed live recipe
authority; it also recovers a stale `running` state after an OS or process loss when both the
authenticated control channel and the recorded runtime port are no longer active.
On Windows, the supervisor also retries transient atomic state-file replacement contention within
a bounded one-second window, so a successful stop cannot leave a stale `running` record behind.
On ASUS-GEI, the hidden limited-user logon task `EllmosOceanFullUserStart` now launches the exact
`ocean-full-laptop-hafenlicht-20260829` checkout and `C:\_Local_DEV\ocean-full`; its controlled
demand-start acceptance returned task result `0` with one supervisor, one child and one listener.
This proves the configured logon path, not an actual reboot. The former BACH session sidecar was
then stopped through BACH's own CLI.

## Status

**This repository:**

| | |
|---|---|
| Architecture skeleton | present, 13 bundles referenced |
| BACH extraction baseline | present — 114 source-declared names; historic 113-name runtime bar retained; re-audited 2026-08-18 (106 handler classes, +1 vs. the 2026-08-08 baseline — traced to a host-suffixed duplicate file in BACH, `upgrade-WORKSTATION-LG.py` alongside `upgrade.py`; not fixed here, BACH is out of scope for this repository's changes). `registered_names` unchanged at 114. |
| K9-1 data/checkpoint gate | two carrier fixtures green; adapter and BACH equivalence remain open |
| Installer and lifecycle | **Resolve, Verify, source-provenance pins, SHA-pinned Fetch/Place, exact provider bindings, sandboxed skill Activate, append-preserving activation logging, target-validated Roll back, installed-snapshot recovery, runtime start/status/stop/restart and delegated user bootstrap are implemented.** The accepted Windows Full Ocean workspace is `C:\_Local_DEV\ocean-full`. It verifies **28/28** OCEAN-family bundle pins, resolves **54 of 65 module references and all 80 skills**, has no missing required component, reports `full_composition: true`, and runs at `http://127.0.0.1:8810/control/`. The eleven unresolved module references are optional. The separately placed `automation-runtime` provider passed native provider/scheduler readback, immutable-receipt, redaction and bounded-statistics acceptance at commit `c2de7188626510b181c4ecf2708c15f2395e32aa`. The active-runtime preflight stops a second `up --apply` before Fetch/Activate can write. The product-owned origin redirects Root to OCEAN and clears legacy provider PWA workers/caches without clearing cookies or other browser storage. Live HTTP and a real browser confirm `307 / → /control/`, the `OCEAN Full Dev` surface and no TerminPilot product markers. A real stop/start/stop/start cycle proves the Windows state-file fix. The suite now contains **150 passing tests plus 2 passing subtests**. This is a composition-complete private Full Dev build for its declared required scope, not an OPEN OCEAN release or BACH-parity claim. Full Ocean selection commit `1b461c9cb900ada15b8e104f2586a6b4a1ea5278` is adopted in canonical recipe `main`, whose post-adoption readback is `b13f1b11626141d6dc6927028dc10008bc406866`. See the [staged build plan](architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md). |
| Runtime | **available for private Full Dev** through the declared `runtime.host` provider `ellmos-core`, with the resolved `unified-gui.host` exposed as the OCEAN operator surface; an OPEN OCEAN runtime is not shipped and the private provider is not a public dependency |
| Recipes | maintained in the recipe repository, not here |

**The traffic light** — release condition 1 turns green when every referenced bundle is green,
meaning each of its components is public and checked. Scope matters here: this repository's
skeleton references exactly **13** of the ecosystem's ~30 bundles (see [the skeleton](architecture/open-ocean.skeleton.v1.json));
condition 1 is about those 13, not the wider catalog.

| | |
|---|---|
| Bundles referenced by this repository | **13** |
| Of those, components verified public (2026-08-18) | **13 / 13** |
| Unique components checked | 18 modules, 1 access-surface repository (`ellmos-homebase-mcp`), 27 skills (in the public `ellmos-ai/skills` catalog), 1 optional software app (`MediaBrain`) — all confirmed public via live `gh repo view`/catalog lookup, not the modules' own manifest `visibility` field (that field records a target classification and can lag the actual GitHub state) |
| Not applicable to this check | 3 `access_surface` refs to commercial agent providers/subscriptions/APIs (no repository, no public/private state) |

None of the four repositories that blocked *other* parts of the wider ecosystem on 2026-08-08
(`ellmos-core`, plus the three that meanwhile went public — `ellmos-scheduler`, `system-explorer`,
`policy-registry`) are referenced by this repository's 13-bundle skeleton at all; they gate bundles
outside this repository's scope (`core-discovery`, `prompt-workflow`, `runtime-options`,
`governance-assurance`, `automation-control`). Condition 1, read strictly for what this repository
actually references, is met as of 2026-08-18. What still blocks publication is conditions 2 and 3
below, not condition 1.

### WORKSTATION-LG fresh install (2026-08-30)

A second, independent Windows host completed the same Full Dev composition on 2026-08-30:
`WORKSTATION-LG`, workspace `C:\_Local_DEV\ocean-full`, target directory absent beforehand (a
genuine fresh install). Input worktrees: `open-ocean` at tag
`ocean-full-laptop-hafenlicht-20260829` (`243a703c60e295f050a2dc68bdde13ef8e847d29`),
`ellmos-development-system` at `1b461c9cb900ada15b8e104f2586a6b4a1ea5278` — both detached and
clean. Pre-install tests: pytest 137/137, unittest 125/125, ruff clean, `compileall` exit 0.

The plan before apply reported 28/28 bundles (`all_ok`), 80/80 skills, but only 51/65 modules
(`full_composition: false`) — three required providers were not yet local. Apply fetched them by
git-fetch-at-SHA into `<workspace>\modules\`: `automation-registry@ad40de721615518e409b53b00ed4b2a49840db28`
and `automation-runtime@c2de7188626510b181c4ecf2708c15f2395e32aa` (both from
`dev-bricks/automation-master.git`), and `software-endpoint-registry@ec50c92319ba8fc262d695b86818fc85666feff7`
(from `ellmos-ai/system-explorer`) — all three then clean, detached checkouts. After apply: 28/28
bundles, 54/65 modules, 80/80 skills, no missing required component, `full_composition: true`,
runtime `ellmos-core` at `http://127.0.0.1:8810/control/`.

A full `down`/`start` lifecycle cycle was exercised (stopped, port freed, no stale processes, then
running again with no state reuse), followed by the same HTTP/browser/process checks as above.

The hidden limited-user logon task `EllmosOceanFullUserStart` (trigger `AtLogOn`, principal
`lukas`, `LogonType Interactive`, `RunLevel Limited`, hidden) launches `pythonw.exe` against the
pinned input worktree's `ocean.py start --workspace "C:\_Local_DEV\ocean-full"`. One controlled
on-demand start on 2026-08-30 returned `LastTaskResult 267009` (`SCHED_S_TASK_RUNNING`, the
expected code for an intentionally still-running server process, not `0`) with one supervisor
(PID 6460) and one child (PID 37676), both under `pythonw.exe`, the child being the sole listener
on `8810`; `full_composition: true` and the product identity held afterward. No actual device
reboot was tested.

No BACH session sidecar was ever running on this host (`service.running: false`, `pid: null`), so
none was stopped; BACH code, databases, tasks and configuration are unchanged. No user account was
created for OCEAN on this host — a deliberate decision, not an installation gap; see TODO for the
device-bound OS-account coupling this is meant to become.

## Release conditions

This repository carries a conditional publication gate (`PRIVATE.txt`, committed on purpose so
the gate is visible where visibility is switched). It opens when all four are demonstrably met:

1. **Green components** — every referenced bundle is green: each of its components public and
   checked. **Met as of 2026-08-18** for this repository's 13-bundle scope — see the traffic-light
   table above.
2. **Sluice test passed** — the whole line works end to end: a fresh install from these recipes
   reaches a working state on a machine that is not the development host. **Not met yet.** The
   installer seam remains foreign-host integration-proven by the 2026-08-20 Mac Studio run. On
   2026-08-29 the development host additionally completed a real Full Dev plan/apply/start/status/
   stop/restart cycle. The initial root-page acceptance proved transport only and was later found
   to be the provider's TerminPilot domain surface, not OCEAN. The corrected cycle now exposes and
   browser-verifies the resolved operator UI at `127.0.0.1:8810/control/`. A later persistent-profile
   regression additionally made OCEAN own Root, manifest, offline identity and worker cleanup on
   that origin. The development-host composition now also resolves the distinct
   `module:automation-runtime`, has no missing required component and reports
   `full_composition: true`. That materially advances OCEAN, but it is still not the required fresh
   foreign-host full-system proof. The current apply verifies all 28 refs against Full Ocean
   selection commit `1b461c9cb900ada15b8e104f2586a6b4a1ea5278`, now adopted into canonical recipe
   `main` with post-adoption readback `b13f1b11626141d6dc6927028dc10008bc406866`. See
   `architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md` for the exact evidence and remaining breadth.
3. **Parity for the release scope** — the system performs at the level it claims to cover. A
   smaller installable core is a build stage, not a release. The current source audit records
   114 reachable names while retaining the historic 113-name runtime snapshot as the minimum
   commitment; see the [extraction roadmap](architecture/BACH-EXTRACTION-ROADMAP.md). **Re-measured
   2026-08-18** (read-only, BACH untouched): the 114-name bar is unchanged and still current; see
   `architecture/bach-parity-baseline.v1.json` → `re_audit_2026-08-18`. This condition asks for more
   than a name count, though: [Cluster 9's operation matrix](architecture/BACH-EXTRACTION-ROADMAP.md#cluster-9-operation-matrix)
   is the only cluster with active work (8 of 9 clusters have not started), and within it 0 of 30
   command names carry `accepted` (functionally-equivalent) status yet — 20 are `candidate-partial`,
   9 are `gap`, 1 is `alias`. Condition 3 is therefore **not close to met**; it depends on the same
   installer/runtime work as condition 2.
4. **Publication check passed** — law, privacy and licensing reviewed with no blockers. **Run
   2026-08-18** (`repo-publish-check` skill, 10 gates) — verdict and local report:
   `.GITHUBBOT/workflows/repo-publish-check/reports/ellmos-ai__open-ocean_2026-08-18.md` (kept
   local per the skill's own rule, not shipped in this repository).

Condition 2 is the one this repository is named after. Opening the sluices and watching whether
the water actually arrives is the test that no amount of correct manifests can substitute for.
Of the four conditions, 1 and 4 are addressed. Condition 2 now has a verified transactional seam
and a working development-host runtime, but still lacks a complete fresh foreign-host installation;
condition 3 still lacks BACH functional parity. `PRIVATE.txt` therefore remains in force.

## Licence

MIT, chosen by the owner on 2026-08-08 and committed as [`LICENSE`](LICENSE). That settles the
licence part of release condition 4; its law and privacy parts stay open until the publication
check has been run.
