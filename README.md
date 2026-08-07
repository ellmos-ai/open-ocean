# open-ocean

**Free the ocean.**

The free community full system of the ellmos ecosystem: recipes, bundles, and composition.

*[Deutsch](README_de.md)*

> **Private build.** This repository is being assembled in private and opens when the water
> reaches the ocean. Its release conditions are written down and checkable — see
> *[Release conditions](#release-conditions)*.

---

## Read this first: what v0.x is, and what it is not

**open-ocean v0.x is a declarative recipe layer for agent CLIs you already run. It is not a
standalone application.**

That sentence is the most useful thing on this page, so it comes before the pitch. There is no
installer yet, and there is no runtime of our own yet: every candidate for one is either private
or still only declared. What exists here are **recipes** — machine-readable manifests describing
which components form a working unit, which role each fills, what it provides and consumes, and
which alternatives were weighed. You bring the runtime; the recipe tells you what to put in it.

An installer is planned and is what turns "described" into "installed". Until it ships, treat
this repository as documentation you can compute with, not as software you can start.

## Why a recipe is worth publishing at all

A bundle manifest is a **recipe = seed + ingredient list**.

The ingredient list is the easy half. Every bundle, stack and system here resolves completely
into a flat list of repositories, skills and agent roles — and every one of those is public and
findable on its own.

The **seed** is the half that does not resolve: which parts belong together, which role each
fills, which alternative was chosen under which criteria, in what order things are built. That
knowledge is not recoverable from the ingredient list. **Having all the modules is not having the
system** — which is exactly why the recipes are the interesting thing to publish and not an
afterthought.

## Where the name comes from

The ecosystem names its layers after water, because the metaphor carries the architecture rather
than decorating it:

| Term | What it is |
|---|---|
| **stream / water** | the process itself — data, work, results flowing through everything |
| **Bach / Rinnsal** | the wild, grown streams: the original personal full instance |
| **water pipes** | the same water, tamed and modularised — modules and bundles |
| **ocean** | the full system; the end of the line Bach → Rinnsal → ocean |
| **open-ocean** | the part that belongs to everyone: the free community full system |

The governing rule is a conservation law: **extraction changes the bed, never the water.**
Restructuring must preserve function. "Same volume of water" means functional parity — which is
also the release bar this repository has to clear.

## What is in here today

13 bundles, in two rings. Every component of every one of them is publicly available today,
optional components included — that is precisely the admission criterion.

**Ring 1 — the functional core.** The smallest set that adds up to a working system: memory both
short and long, access to an agent, selection knowledge, and a way to acquire knowledge.

| Bundle | Class | Pillar | Components | What it carries |
|---|---|---|---|---|
| `ellmos-working-memory-bundle` | platform | memory | 5 | session state: what was captured, what is still open |
| `ellmos-memory-human-context-bundle` | platform | memory | 6 | durable memory and the user model |
| `ellmos-agents-bundle` | platform | control | 7 | access to the runtime — the stand-in for a runtime of our own |
| `ellmos-coordination-choice-bundle` | choice | control | 2 | selection knowledge: the visible proof a recipe beats a list |
| `ellmos-knowledge-bundle` | platform | — | 8 | finding and preparing knowledge |

**Ring 2 — breadth at no extra risk.** Equally clean, and useful from day one.

| Bundle | Class | Pillar | Components |
|---|---|---|---|
| `ellmos-doc-handler-bundle` | domain | domain | 11 |
| `ellmos-media-production-bundle` | domain | — | 7 |
| `ellmos-daily-life-bundle` | domain | uas | 6 |
| `ellmos-voice-media-assist-bundle` | domain | uas | 3 |
| `ellmos-health-assist-bundle` | domain | uas | 2 |
| `ellmos-briefing-bundle` | domain | uas | 1 |
| `ellmos-finance-assist-bundle` | domain | uas | 1 |
| `ellmos-knowledge-search-choice-bundle` | choice | — | 1 |

60 component slots in total. `manifests/bundles.catalog.v1.json` is the index.

**What is deliberately absent:** bundles whose components are not all public yet. A recipe with
its alternatives trimmed away to make it publishable loses the very seed that made it worth
having, so those wait rather than ship diminished.

## Status: the traffic light

Rollout is incremental, not a big bang. A bundle goes green when each of its components is public
and checked; open-ocean goes green when everything it references is green.

| | |
|---|---|
| Bundles green-capable | **13** |
| Blocked by components that are not public | 17 further bundles |
| Largest single lever | four private repositories block seven bundles between them |

Whether those four become public is a decision for the owner of the ecosystem, and no automated
process anticipates it.

## Release conditions

This repository carries a conditional publication gate. It opens when all four are demonstrably
met:

1. **Green components** — every referenced bundle is green in the register above.
2. **Sluice test passed** — the whole line works end to end: a fresh install from these recipes
   reaches a working state on a machine that is not the development host.
3. **Parity for the release scope** — the system performs at the level it claims to cover.
4. **Publication check passed** — law, privacy and licensing reviewed with no blockers.

The gate itself lives in the local working copy as `PRIVATE.txt` and is deliberately not
committed: it is a local control file, so a bot that only ever sees the remote still has to
consult the working copy before touching visibility.

## How these files got here

The recipes are not maintained here. They are **projected** out of a private composition
repository by `tools/export_from_source.py`, and what gets removed or rewritten on the way is
declared as data in an export contract rather than buried in the script:

- host names, internal paths and unresolvable internal identifiers are stripped or neutralised
- components carrying operating data of a real organisation are excluded — the source keeps them,
  this projection does not
- the private source repository is never named

Two properties make the result checkable rather than merely asserted:

- **Reproducible.** Run the export twice against the same source state and the second run
  produces no diff. `--check` reports drift instead of writing.
- **Verifiable.** Every manifest carries a `content_hash` over its exported form, and
  `manifests/export-receipt.v1.json` records the source state each file came from. A hash that
  belonged to the unexported original would make an honest file look tampered with, so the
  export re-pins them.

```bash
python tools/export_from_source.py --source <path-to-source> --check
```

## Licence

Not yet settled. It is one of the four release conditions and will be fixed before this
repository opens.
