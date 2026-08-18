# ocean-dev build plan — Durchgang 1

> **Status: living plan, not a finished system.** Records what exists, what was built in this
> pass, and what the next passes need to do, in the target order the user set. Updated as each
> pass lands; superseded sections are struck through with a date, not deleted.

## 0. Origin and the decision this plan executes

- **Ticket:** `T-20260818-903104603` ("open-ocean Installer+Laufzeit bauen") — raised the
  weichenfrage a/b/c: build ocean-runtime as its own project (a), fold it together with the
  July-deferred generic `ellmos-installer` into one build effort (b), or reconfirm the deferral (c).
- **User decision (2026-08-18 briefing): (b).** The July decision `D-20260731-005` deferred the
  generic installer with a named reopening condition: *"installationen dann wenn wir systeme und
  bundle/stacks anbieten und dafür repos machen"*. That condition is now met — `open-ocean` is a
  system, `bundles` is the recipe repository, both exist. The deferral lifts for this purpose
  specifically; it does not retroactively mean "build a generic installer for its own sake".
- **Source condition matrix:** `T-20260818-229528104` (kept in `USER/`, read-only reference here —
  not re-litigated). It measured PRIVATE.txt's four release conditions and found conditions 2
  (sluice test) and 3 (BACH parity) both blocked on the same missing thing: no installer, no
  runtime. This plan is the direct response.

## 1. Terminology (user briefing, 2026-08-18)

| Term | Meaning |
|---|---|
| **ocean-dev** | the local development system — what runs and gets tested on a dev host today. Not a separate repository or product; a *mode* of using this one, where "installed" can mean "already present because this is where it's built" rather than "freshly fetched onto a bare machine". |
| **ocean-full / open-ocean** | the published, BACH-parity full system — this repository's eventual release, gated by `PRIVATE.txt`. |
| **ellmos-systems** | OS-level layer: BACH, rinnsal, ocean. Broad, zweckoffen, own lifecycle (matches the `os-stack` class in `.STACKS/STACK-MAPPING.md`). |
| **ellmos-stacks** | zweckbezogene Rezepte — the bundle/stack composition layer `open-ocean` *consumes* (`ellmos-ai/bundles`), not a peer of the systems above it. |

`open-ocean` therefore sits in the **ellmos-systems** column, one level up from the stacks it
resolves. That placement is why its installer cannot be "just another stack installer" — it has to
turn a *recipe of stacks* into a *system*, which is exactly the gap `INSTALLER-TARGET.md` names.

## 2. What already existed going into this pass

- **The recipe layer** (`ellmos-ai/bundles`): 30 bundle manifests, `content_hash`-sealed,
  `choice_groups[]` with `default_selection`. 13 of them are `open-ocean`'s scope
  (`architecture/open-ocean.skeleton.v1.json`, rings 1 + 2).
- **`.MODULES/_scripts/`** (OneDrive, not this repo): `module_resolver.py` (`ModuleResolver` —
  looks up a catalogued module ID against `modules.catalog.json` and returns its local path/repo/
  visibility) and `validate_composition.py` (validates a `stack.v2.json` against the module
  catalog and `composition.rules.json`, including `choice_groups` structure).
- **The sovereign-private pilot installer** (OneDrive `.AI/.STACKS/sovereign-private/_dev/pilot/`):
  a working, tested, manifest-driven multi-repo installer with a gate chain, an airgap branch, and
  a lock file — analysed in full in `INSTALLER-REUSE-BEFUND_2026-08-07.md`.
- **The BACH mechanisms** the reuse befund named as portable, not importable: update's
  Backup→Apply→Verify→Rollback phase model, the `dist_type` CORE/TEMPLATE/USER split, and the
  skill `DependencyResolver`.
- **The architecture skeleton** for this repository already declared *what* the installer has to
  do (`INSTALLER-TARGET.md`: Resolve, Verify, Fetch, Place, Activate, Roll back) and what it must
  never do (decide visibility, resolve an unverified recipe, fetch access surfaces, write into the
  recipe repository) — written before any code, precisely so the gap would be visible.
- **What did not exist:** anything that reads the recipe layer's `components[]` and turns it into
  a concrete plan. `INSTALLER-REUSE-BEFUND_2026-08-07.md` Sec. 6.4 named this as the #1 missing
  piece — "Kein Beteiligter kennt 'Bundle enthält Komponenten'" — blocking every step after it.
- **The architectural precedent this pass reuses without rebuilding it:** the sovereign-private
  `ellmos-core` + `ellmos-unified-gui` mount work from the same day (Sovereign-Ticket
  `T-20260816-361197589` Stufe 4) is a *different* codebase (a private enterprise product, not
  `open-ocean`), but it is the concrete proof, on this very system, that "one process, a real
  login, a real end-to-end smoke, not three half-built pieces" is achievable in a single session
  here — the discipline this plan follows, not code it imports.

## 3. What this pass (Durchgang 1) built

**Scope: the Resolve and Verify steps, plus a read-only slice of Activate. Fetch, Place, the write
side of Activate, and Roll back are explicitly NOT in this pass — see Sec. 5.**

### 3.1 `tools/resolve_bundles.py` — Resolve + Verify

- Reads `architecture/open-ocean.skeleton.v1.json`'s pinned `bundle_refs[]` for a chosen ring
  (`1`, `2`, or `all`).
- **Verify:** for each bundle, reads `bundle.v1.json` from an external `--bundles-root` checkout
  (never copied into this repository, per the skeleton's own `not_yet_present` note) and
  recomputes its `content_hash` with the *same* algorithm the recipe repository uses
  (`bundles/tools/export_from_source.py:canonical_hash` — sorted, compact JSON, sha256, excluding
  the hash field itself; the algorithm is duplicated here deliberately rather than imported, so
  this repository stays runnable without a sibling checkout on `PYTHONPATH`). Checks it three ways:
  the file's own declared hash against a fresh computation (catches tampering/corruption) and
  against the skeleton's pin (catches a stale skeleton). A verified-and-tested distinction: a
  synthetic test proves a content edit with a *stale* declared hash still passing the pin check is
  caught by the self-consistency check specifically — the naive "declared vs. pinned" comparison
  alone would have missed it.
- A failed Verify **stops the run** (exit 2) before any component is resolved, matching
  `INSTALLER-TARGET.md`'s "a failed hash check stops the run; it does not warn and continue".
- **Resolve:** expands each verified bundle's `components[]` into a flat, de-duplicated list,
  merging duplicates' `from_bundles` and taking the strictest `requirement` level across bundles.
  Applies `choice_groups[]` at their `default_selection` only — the minimal, already-legitimate use
  of an existing field, not the general min/max choice-applier `INSTALLER-REUSE-BEFUND` Sec. 6.4
  point 2 separately flags as missing (that stays a named follow-up, Sec. 5).
- Classifies and resolves each component by kind: `module:<id>` against
  `modules.catalog.json` (same lookup `ModuleResolver` performs, re-implemented here rather than
  imported so this repository does not depend on an OneDrive path being importable — the *catalog
  file* is still read from there via `--modules-catalog`, only the code is not shared);
  `skill:<name>` against the public `ellmos-ai/skills` registry, matched by `name` (the crosswalk
  file the component-registry-bindings contract names,
  `bundles/manifests/skills.registry.crosswalk.v1.json`, does not exist in the bundles checkout
  yet — documented as a gap, not silently assumed to match); `access_surface:<id>` is reported and
  **never fetched**, per `INSTALLER-TARGET.md`'s explicit "must not do".
- 26 unit/integration tests, synthetic fixtures throughout (same convention as
  `test_audit_bach_handlers.py`) so the suite is host-independent — it must pass with no OneDrive
  present at all.

**Real run against ring 1 on this development host** (2026-08-18, evidence, not a fixture):

```
Verify: 5 bundle(s) checked, all_ok=True   (all five ring-1 bundles hash-verified)
Components: 27 total — 22 resolved, 4 not-fetched-by-design (access surfaces), 1 unresolved
```

The one unresolved finding is real, not manufactured: `module:memory-hooker` (the bundle's
component ref) vs. `memoryhooker` (the catalog's actual module ID) — a hyphenation drift between
the recipe layer and the module catalog. Exactly the class of finding this tool exists to surface;
fixing the catalog or the bundle is catalog/recipe maintenance, out of scope for this repository.

### 3.2 `tools/host_adapters.py` — a read-only slice of Activate

`INSTALLER-TARGET.md` names Activate as "the one step that has no equivalent in a package
manager: the target is an agent, not a filesystem" and lists as an open question whether the
installer targets one host agent CLI, several, or an abstraction over them.

This pass answers that with a `HostAdapter` Protocol and exactly one concrete implementation,
`ClaudeCodeHostAdapter` — following **D-20260817-005** ("controlroom" E4, Multi-Agent-Reichweite,
ENTSCHIEDEN **[B, Claude als Referenz]**): vendor-neutral interface from the start, one reference
implementation, more hosts (Codex, Gemini/agy, Kimi) addable later without touching any caller.
That decision was made for a different interface (controlroom); it is applied here because the
build order for this ticket names it as the governing precedent for every new interface in this
programme.

Deliberately read-only in this pass: `skill_present(name)` answers "would Activate have anything
to do", not "do it". A write-side Activate (and its Roll back counterpart) is a materially
different risk profile — mutating a live agent CLI's configuration — and is scoped as its own
follow-up rather than appended here under time pressure (Sec. 5).

**Real run, ring 1, `--activation-check claude-code` (this host, 2026-08-18):** 9 of 9 ring-1
skills already present under `~/.claude/skills/`. On a dev host, that is the expected and correct
answer — ocean-dev accumulates skills through ordinary use, unlike a bare install target.

### 3.3 What Durchgang 1 deliberately did not touch

- **Fetch/Place** for `module:` components. On this dev host every ring-1 module the catalog
  *does* resolve is already present locally (`ModuleResolver` and this pass's re-implementation
  both look up an existing local path, not a remote fetch target) — so there was nothing to
  meaningfully fetch for a demonstration on ocean-dev specifically. A fresh-machine Fetch/Place
  step is real work, is genuinely different from what exists, and is Sec. 5's next item.
- **Write-side Activate + Roll back.** Named above.
- **The general choice-applier** (min/max cardinality, not just `default_selection`) and **SHA
  pinning for module fetch** — both named gaps in `INSTALLER-REUSE-BEFUND` Sec. 6.4 that this pass
  did not need for ring 1 (its one choice group has exactly one candidate to apply, and no module
  needed fetching), so building them now would be speculative rather than driven by an actual
  requirement.
- **BACH parity work.** Out of scope for this pass by design — see Sec. 6.

## 4. Guardrails carried forward from prior decisions

- **E4 (D-20260817-005): vendor-neutral from the start, Claude as reference**, applied to
  `host_adapters.py` above and to any future new interface this programme adds.
- **E5 (D-20260817-006-adjacent, "Stores bleiben kanonisch"): never consolidate.** USMC, Gardener,
  `taskplan.db`, lock files and the skills registry all stay their own canonical stores; nothing in
  this plan proposes a shared schema. Where a unified *view* is useful (e.g. a single resolve
  report naming components from several stores), the view is additive, not a merge of the
  underlying data.
- **Hosted gates:** `sovereign-hosted` and any hosted variant of `open-ocean` stay outlined only,
  never built without explicit per-gate user sign-off — unaffected by this plan, not touched here.
- **W-07** (the `ellmos.stack.v2` schema collision between `.STACKS/` composition manifests and
  `.SYSTEMS/stacks/` deployment projections): not implicated by this plan — `resolve_bundles.py`
  reads `ellmos.bundle.v1` and `ellmos.open-ocean-architecture-skeleton.v1` documents, neither of
  which is a party to that collision.
- **VISIBILITY-POLICY / PRIVATE.txt:** this plan explicitly stays inside the "editing is allowed,
  publication is not" boundary. Nothing here changes `open-ocean`'s GitHub visibility or touches
  `PRIVATE.txt`'s own text; the release conditions it names are *measured*, never declared met by
  fiat.

## 5. Target order and staged work packages

The order below is the one the build authorisation set: **minimal installable ocean-dev core →
foreign-host smoke → BACH-parity cluster.** Each stage only starts once the one before it is real,
not merely planned.

### Stage 1 — minimal installable ocean-dev core

- [x] **Resolve + Verify** (`tools/resolve_bundles.py`) — Durchgang 1, this document, Sec. 3.1.
- [x] **Read-only Activate check** (`tools/host_adapters.py`) — Durchgang 1, Sec. 3.2.
- [ ] **Fetch + Place for `module:` components not yet locally present.** Needs: a source-type
  dispatch (`local-directory` = already resolved, nothing to do; `git-repository` = clone/pull);
  the pilot installer's `install_module` (`install_sovereign.py:145-222`) is the pattern to port,
  **not import** — same posture as the BACH mechanisms, ported because `open-ocean` cannot depend
  on a private, non-packaged OneDrive script tree. Its known bug (the silent default-branch
  fallback on an unresolvable ref, `INSTALLER-REUSE-BEFUND` Sec. 5.4) must NOT be carried over.
- [ ] **Write-side Activate**, one host first (Claude Code, same E4 precedent): install a resolved
  skill into `~/.claude/skills/` when `skill_present()` is false, with the Roll back counterpart
  built in the same session as the write path — not after it, per `INSTALLER-TARGET.md`'s own
  ordering of the six steps.
- [ ] **A single-command "ocean-dev up" entry point** that chains Resolve → Verify → Fetch/Place →
  Activate for a chosen ring, with `--dry-run` before any write (matching the pilot installer's
  own `--dry-run` convention).
- **Definition of done for this stage:** running the entry point against ring 1 on a *second* dev
  host (not this one) reaches a state where all resolvable ring-1 skills are activated there too,
  starting from whatever that host already has — the honest, host-plural version of "installable
  core" before a genuinely bare-machine sluice test is attempted.

### Stage 2 — foreign-host smoke (Mac Studio)

- **Blocked, documented rather than attempted this pass.** Mac Studio's OneDrive sync client is
  down: `pgrep -fl OneDrive` finds no running process, `.TOPICS/.AI/.MODULES/modules.catalog.json`
  there is 10+ days stale, and 105 unresolved conflict copies have accumulated
  (`T-20260818-179999731`, `BLOCKED`, external-state). Network-layer reachability (SSH,
  `~/compute/`, `~/.venvs/science`) was separately verified fine on 2026-08-18
  (`T-20260818-229528104`) — the blocker is content sync, a different layer, not connectivity.
- **This plan does not restart the Mac Studio OneDrive client.** That ticket is explicit that a
  blind SSH restart of a 24/7 production host without GUI diagnosis is the wrong move without
  either physical/VNC access or explicit user sign-off, and this ticket carries no mandate to
  operate on Mac Studio's infrastructure.
- **When the sync ticket resolves:** re-run `python -m unittest discover -s tests` there first (it
  needs no OneDrive access at all — the suite is synthetic-fixture-only by design, see Sec. 3.1),
  then a real `resolve_bundles.py --ring 1` run against the *live, resynced* catalog and bundles
  checkout, then the Stage 1 entry point once it exists. A smoke on a host with a stale catalog
  would prove nothing except that the catalog was stale — worse than not testing, because it would
  look like a foreign-host result while actually being a sync-outage artifact.

### Stage 3 — BACH-parity cluster

- **Not started, not due yet.** `BACH-EXTRACTION-ROADMAP.md`'s own binding order is "Cluster 9
  first" (already the only cluster with any work — 0/30 `accepted`, see the operation matrix),
  followed by Cluster 1 (memory/knowledge), 3 (tasks/automation), 5 (multi-agent/orchestration), 7
  (self-extension/dev tools), 4 (documents/media), 6 (communication), 8 (cognitive control), and
  finally 2 (personal-life services, held out of the free core for separate privacy/legal/product
  reasons).
- Stage 1's ring-1 bundles (`agents`, `coordination-choice`, `knowledge`, `memory-human-context`,
  `working-memory`) already overlap Cluster 1 and parts of Cluster 3/5 in *subject matter* — but
  functional-parity proof (the thing PRIVATE.txt condition 3 actually asks for) is a distinct,
  much larger claim than "the recipe references a plausible replacement module". Nothing in Stage
  1 should be read as advancing Cluster 9's 0/30 `accepted` count; it did not touch that matrix.
- Next concrete step, when this stage starts: `tools/check_k9_data_contract.py`'s existing
  fixture-equivalence pattern is the template — run old (BACH) and new (open-ocean) implementations
  against the same anonymized fixtures, BACH read-only throughout (the buildweek-no-push lock
  applies regardless of that lock's own expiry, because this repository's own rule is BACH stays
  read-only for parity work independent of any external lock state).

## 6. Honesty check — what this plan is not claiming

- Ring 1 is **resolvable and verifiable**, and on *this* dev host, **mostly already active**. It is
  not yet **installable onto a machine that does not already have it** — that is Stage 1's
  remaining half.
- Nothing here moves `open-ocean` closer to lifting `PRIVATE.txt`. Conditions 2 and 3 both still
  read "not met" honestly; this plan is the first concrete step toward them, not a claim that
  either is now satisfied.
- `memory-hooker`/`memoryhooker` and `software:MediaBrain` (an unhandled component kind, surfaced
  when running `--ring all`) are real, live findings from running the tool against real data, kept
  as findings rather than quietly patched around, because patching the catalog or adding a
  `software_app` resolver were not asked for in this pass and are better done deliberately.
