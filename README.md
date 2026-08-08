# open-ocean

**Free the ocean.**

The free community full system of the ellmos ecosystem.

*[Deutsch](README_de.md)*

> **Private build, and early on purpose.** This repository exists before the system does, so the
> architecture has somewhere to live while it is being decided. It opens when the water reaches
> the ocean — see *[Release conditions](#release-conditions)*.

---

## Read this first: this repository is a building site

**There is no system here yet.** No installer, no runtime of our own, and deliberately no copies
of the recipes. What is here is the architecture of what is being built: which recipes the system
will consume, where they live, and what the installer has to become.

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

The system is not being written next to the original instance, and the original is not being
rebuilt. It emerges by continued **extraction**: modules flow out of the original, and the
original then wires them back in, replacing its own internals. It does not become a museum piece.
It carries on as a straightened river — no longer entirely natural, but connected to the water
and still supplied.

## What is actually in here

```
architecture/
  open-ocean.skeleton.v1.json   which recipes the system intends to consume, pinned by hash
  INSTALLER-TARGET.md           what the installer has to become, and what it must not do
  BACH-EXTRACTION-ROADMAP.md    extraction order, parity gates and Cluster 9 kernel map
  bach-parity-baseline.v1.json  machine-readable registry and Cluster 9 coverage baseline
tools/
  audit_bach_handlers.py        side-effect-free source audit against that baseline
PRIVATE.txt                     the publication gate, committed on purpose
```

The skeleton references 13 bundles in two rings — the functional core, and breadth around it. It
**references** them: no manifest is copied here. Copies would fork the moment the recipe
repository moves on, and would make this repository look further along than it is.

## Status

**This repository:**

| | |
|---|---|
| Architecture skeleton | present, 13 bundles referenced |
| BACH extraction baseline | present — 114 source-declared names; historic 113-name runtime bar retained |
| Installer | **not built** — decided in principle, deferred, now due again |
| Runtime of our own | **not available** — every candidate is private or only declared |
| Recipes | maintained in the recipe repository, not here |

**The traffic light** — release condition 1 turns green when every referenced bundle is green,
meaning each of its components is public and checked:

| | |
|---|---|
| Bundles green-capable | **13** — the ones this skeleton references |
| Blocked by components that are not public | 17 further bundles |
| Largest single lever | largely resolved on 2026-08-08 — three of the four repositories are public; `ellmos-core` alone still blocks three bundles |

Three of those four became public on 2026-08-08 by the owner's decision — `ellmos-scheduler`,
`system-explorer` and `policy-registry` — which lifted the private-repository block from
`system-knowledge` and `personal-ops` at the required-component level. The fourth, `ellmos-core`,
stays private: its own `RELEASE_GATE.md` bars any visibility change until the licence choice and
several security items are settled, and that gate is the owner's to lift, not an agent's. It still
blocks `core-discovery`, `prompt-workflow` and `runtime-options`; `governance-assurance` and
`automation-control` remain blocked by components that were never private but simply do not exist
publicly yet. Until those are resolved, this repository cannot reach the scope its name implies —
which is the honest reason it is still private rather than merely unfinished.

## Release conditions

This repository carries a conditional publication gate (`PRIVATE.txt`, committed on purpose so
the gate is visible where visibility is switched). It opens when all four are demonstrably met:

1. **Green components** — every referenced bundle is green: each of its components public and
   checked.
2. **Sluice test passed** — the whole line works end to end: a fresh install from these recipes
   reaches a working state on a machine that is not the development host.
3. **Parity for the release scope** — the system performs at the level it claims to cover. A
   smaller installable core is a build stage, not a release. The current source audit records
   114 reachable names while retaining the historic 113-name runtime snapshot as the minimum
   commitment; see the [extraction roadmap](architecture/BACH-EXTRACTION-ROADMAP.md).
4. **Publication check passed** — law, privacy and licensing reviewed with no blockers.

Condition 2 is the one this repository is named after. Opening the sluices and watching whether
the water actually arrives is the test that no amount of correct manifests can substitute for.

## Licence

MIT, chosen by the owner on 2026-08-08 and committed as [`LICENSE`](LICENSE). That settles the
licence part of release condition 4; its law and privacy parts stay open until the publication
check has been run.
