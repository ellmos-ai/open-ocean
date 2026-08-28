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

**The released full system is not here yet.** A transactional installer core now exists and has
been exercised on Windows and macOS, but there is still no BACH-parity runtime of our own and
deliberately no copies of the recipes. What is here is the architecture and the first executable
system-building layer: which recipes the system consumes, where they live, and how they are
resolved, verified, fetched, placed, activated and rolled back.

If you are looking for something usable today, it is the recipe layer — a separate repository
that holds the bundle manifests and releases them wave by wave. The recipes are ready months
before the system that consumes them, which is exactly why they are not in here: a repository
that shipped recipes under the system's name would look finished while the system is not.

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

## Status

**This repository:**

| | |
|---|---|
| Architecture skeleton | present, 13 bundles referenced |
| BACH extraction baseline | present — 114 source-declared names; historic 113-name runtime bar retained; re-audited 2026-08-18 (106 handler classes, +1 vs. the 2026-08-08 baseline — traced to a host-suffixed duplicate file in BACH, `upgrade-WORKSTATION-LG.py` alongside `upgrade.py`; not fixed here, BACH is out of scope for this repository's changes). `registered_names` unchanged at 114. |
| K9-1 data/checkpoint gate | two carrier fixtures green; adapter and BACH equivalence remain open |
| Installer | **Resolve, Verify, SHA-pinned Fetch/Place, sandboxed skill Activate, activation logging, and target-validated Roll back are implemented for the currently supported component path; that pinnable Ring-1 slice is integration-proven on a foreign host.** On 2026-08-20 one Mac Studio `--apply` invocation verified all 5 Ring-1 bundles, fetched `WikiStub-Seed` at the catalogued SHA `3476ba2…12458af4`, and activated all 9 Ring-1 skills into an explicit sandbox. Its single 10-entry activation log then rolled back the fetched module and all skills; the live Mac `~/.claude/skills` snapshot stayed identical before, after apply and after rollback. On 2026-08-28 the same pipeline gained direct Full Dev composition from the canonical external `ellmos.system.v1` manifest and private recipe-projection layout. A live read-only run found all 30 manifests and verified 27 pins; it stopped before Fetch/Place/Activate on exactly three stale manifest pins (`core-discovery`, `agent-orchestration`, `dev-lifecycle`). The portable suite is now 110 tests. This is not a full-system install claim: the three pins must first be reconciled in their canonical authority, and the earlier source-type, pinning, and naming gaps still apply. See the [staged build plan](architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md). |
| Runtime of our own | **not available** — every candidate is private or only declared |
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
   reaches a working state on a machine that is not the development host. **Not met yet, but the
   installer seam itself is now foreign-host integration-proven.** A Mac Studio run on 2026-08-20
   performed Resolve, Verify, one real SHA-pinned Fetch/Place and all nine Ring-1 skill activations
   in one `--apply` invocation, then removed all ten writes through the same activation log. This
   closes the previously untried combined mechanism path, not the release condition: the target
   was an explicit sandbox, only one Ring-1 Git module currently has a safe catalogue pin, and the
   run did not produce a complete working ocean runtime from every required component. See
   `architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md` Stage 2 for the evidence and remaining breadth.
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
Of the four conditions, 1 and 4 are addressed. Condition 2 now has a verified transactional
installer seam but still lacks a complete fresh working-system installation; condition 3 still
lacks BACH functional parity. Neither is upgraded by the sandboxed integration proof.

## Licence

MIT, chosen by the owner on 2026-08-08 and committed as [`LICENSE`](LICENSE). That settles the
licence part of release condition 4; its law and privacy parts stay open until the publication
check has been run.
