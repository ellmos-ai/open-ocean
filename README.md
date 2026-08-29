<img src="assets/banner.png" width="100%" alt="open-ocean Banner">

# open-ocean

**Free the ocean.**

The free community full system of the ellmos ecosystem.

*[Deutsch](README_de.md)*

> **Private build, and early on purpose.** This repository exists before the system does, so the
> architecture has somewhere to live while it is being decided. It opens when the water reaches
> the ocean — see *[Release conditions](#release-conditions)*.

---

## Read this first: this repository is a building site

**The released public full system is not here yet.** The private OCEAN Full Dev composition is now
runnable on the development host: it can plan, install, start, inspect, bootstrap a user, stop and
restart one declared `runtime.host`. This is the first usable OCEAN product slice, not a BACH-parity
or public-release claim. The verified composition still reports ten missing required modules and
therefore marks itself `full_composition: false`.

OCEAN consumes the recipes from their canonical repository instead of copying them here. The
transaction layer resolves, verifies, fetches, places, activates and rolls back; the lifecycle
layer operates the selected runtime in an explicit local sandbox. The current Full Dev host is the
private `ellmos-core`, selected by capability rather than hard-coded as the future public runtime.

| Repository | What it is | State |
|---|---|---|
| **bundles** | the recipe layer: manifests, catalogue, export tool | private, releasing wave by wave |
| **open-ocean** (here) | the system build: architecture, installer, the thing that consumes recipes | private, early |

## The name, and the architecture it carries

The ecosystem names its layers after water, because the metaphor carries the architecture rather
than decorating it:

| Term | What it is |
|---|---|
| **stream / water** | the process itself — data, work, results flowing through everything |
| **Bach / Rinnsal** | the wild, grown streams: the original personal full instance |
| **water pipes** | the same water, tamed and modularised — modules and bundles |
| **waterfall** | the declarative source: the kit, the recipes, the catalogues |
| **ocean** | the full system; the end of the line Bach → Rinnsal → ocean |
| **open-ocean** | the part that belongs to everyone: the free community full system |

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
- OCEAN Full Dev consumes the existing external `ellmos.system.v1` full-system manifest and all of
  its `bundle_refs[]`. The manifest and private recipes remain in their canonical stores; nothing
  is copied into this repository.

```text
python tools/ocean_dev.py --bundles-root <recipe-projection> \
  --system-manifest <ellmos-development-fullsystem/system.v1.json>
```

Without `--apply` this is a read-only dry-run. A system manifest cannot be combined with a numbered
ring; partial work is selected adaptively as a separate bundle cycle, not by silently truncating
the declared Full Dev composition.

The product lifecycle is exposed at the repository root:

```text
python ocean.py plan <composition arguments>
python ocean.py up <composition arguments> --apply
python ocean.py status --workspace <local-sandbox>
python ocean.py user add --workspace <local-sandbox> --username <name> --email <address>
python ocean.py down --workspace <local-sandbox>
```

Run `python ocean.py --help` and the respective subcommand help for the complete arguments. User
passwords are prompted without echo and are never passed as process arguments; local automation
may use `--password-stdin`.

## Status

**This repository:**

| | |
|---|---|
| Architecture skeleton | present, 13 bundles referenced |
| BACH extraction baseline | present — 114 source-declared names; historic 113-name runtime bar retained; re-audited 2026-08-18 (106 handler classes, +1 vs. the 2026-08-08 baseline — traced to a host-suffixed duplicate file in BACH, `upgrade-WORKSTATION-LG.py` alongside `upgrade.py`; not fixed here, BACH is out of scope for this repository's changes). `registered_names` unchanged at 114. |
| K9-1 data/checkpoint gate | two carrier fixtures green; adapter and BACH equivalence remain open |
| Installer and lifecycle | **Resolve, Verify, SHA-pinned Fetch/Place, sandboxed skill Activate, activation logging, target-validated Roll back, runtime start/status/stop/restart and delegated user bootstrap are implemented.** A live Windows Full Dev run on 2026-08-29 verified all 29 pinned bundles, resolved 51 modules and 62 skills, installed the skill set into an explicit sandbox and reached a healthy web login surface. Start → stop → restart was independently checked. The suite now contains 114 passing tests. Twenty-six module references remain unresolved; ten of them are required by the current Full Dev manifest. See the [staged build plan](architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md). |
| Runtime | **available for private Full Dev** through the declared `runtime.host` provider `ellmos-core`; a public OCEAN runtime is not shipped and the private provider is not a public dependency |
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
   stop/restart cycle and reached a healthy web login surface. That materially advances OCEAN, but
   it is neither a fresh foreign-host full-system proof nor a complete composition: ten required
   modules are still missing. See `architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md` for the exact
   evidence and remaining breadth.
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
