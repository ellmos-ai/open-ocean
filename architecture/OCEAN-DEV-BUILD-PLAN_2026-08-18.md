# ocean-dev build plan — Durchgang 1 + 2 + Full Dev composition

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

## 1. Terminology (user briefing, 2026-08-18; superseded names marked 2026-08-29)

| Term | Meaning |
|---|---|
| **ocean-dev** | the local development system — what runs and gets tested on a dev host today. Not a separate repository or product; a *mode* of using this one, where "installed" can mean "already present because this is where it's built" rather than "freshly fetched onto a bare machine". |
| ~~**ocean-full / open-ocean**~~ | ~~Historical alias for one published BACH-parity system.~~ **Superseded 2026-08-29; these names are not equivalent.** |
| **OPEN OCEAN** | Public OCEAN product and the eventual release built by this repository. |
| **PRIVATE OCEAN** | Private, non-proprietary OCEAN complement. |
| **FULL OCEAN** | Exactly OPEN OCEAN + PRIVATE OCEAN; the local development/test composition. |
| **SPEEDBOAT** | Independent proprietary sibling stack with only explicitly selected OCEAN parts. |
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

### 3.4 Durchgang 2 — Fetch+Place, write-side Activate + Roll back, `ocean-dev up`

Built in this order because it was the order the build authorisation named: Fetch+Place first
(`tools/fetch_place.py`), then write-side Activate + its Roll back counterpart *together*, not
sequentially (`tools/host_adapters.py`, extended), then the single entry point that chains all of
Resolve → Verify → Fetch/Place → Activate (`tools/ocean_dev.py`).

**`tools/fetch_place.py` — the bug this module exists to not repeat, proven, not just avoided.**
Ported (not imported) from `install_sovereign.py`'s `install_module`/`git_clone` pattern, with one
behaviour deliberately dropped: that installer falls back to cloning the default branch when a
pinned `--branch <ref>` does not exist, so a broken pin still produces a "successful" clone of the
wrong commit (`INSTALLER-REUSE-BEFUND` Sec. 5.4). This module refuses instead — a pin that is not a
full 40-hex commit SHA is never handed to git at all (`is_git_sha`, status `unpinnable`), and any
git failure after a valid SHA is accepted removes whatever partial directory was created rather
than leaving a checkout of whatever `git fetch` happened to land on. Proven with a real, disposable
local git repository (no network) in `tests/test_fetch_place.py`:
`test_fetching_the_real_commit_sha_lands_on_exactly_that_commit` and, the load-bearing one,
`test_a_bogus_sha_shaped_pin_fails_loudly_and_leaves_nothing_behind` — asserts both the raised
error *and* that no directory was left on disk. A third test (`test_non_sha_pin_is_refused...`)
proves a bare branch name (`"main"`) is refused before any git command runs at all.

**Scope reality, checked empirically before writing any fetch code:** every `git-repository`-typed
module in the real `modules.catalog.json` (20 of 20, checked on 2026-08-18) carries a semver string
in `version` ("0.1.0" etc.), not a commit SHA — including all three ring-1 git-repository modules
(`WikiStub-Seed`, `project-docs-template`, `build-your-users-mind`), which were separately already
`present_locally: true` on this host regardless. **A real `--ring 1` run against this host's actual
catalog therefore reports every module as either `present` or `unpinnable`/`no-catalog-entry` — never
`fetched`** (see the real-data run below). That is the correct, fail-closed behaviour given the
current catalog data, not a shortfall of this module: the git-fetch *mechanism* is proven by the
synthetic throwaway-repo tests above (including one full apply+rollback run through `ocean_dev.py`
itself, `test_apply_fetches_the_module_and_rollback_removes_it`), not by a real Ring-1 fetch,
because no Ring-1 component currently needs one.

**`tools/host_adapters.py` — write-side `activate_skill` / `rollback_activate_skill`.** Two rules,
both load-bearing: (1) **never overwrite** — an existing destination is a no-op
(`skipped-exists`), which is also what makes rollback-by-removal exact (it only ever removes
something it created into empty space); (2) **the constructor never defaults `skills_dir` to a
host's real, live skill directory.** `skill_present()`'s own read-only default
(`~/.claude/skills`) is unchanged; the *write*-capable caller (`tools/ocean_dev.py`) is the one
responsible for passing an explicit target, and its own default is `<workspace>/skills` — a
sandbox that starts empty, never the live directory, unless an operator passes `--skills-dir`
pointing at it deliberately. Both rules found their way into this document because an earlier
draft of this session let the write path default toward the live directory before catching it;
see Sec. 4 for why this design choice, not a fixed default value, is what's carried forward.
A Windows-specific bug was found and fixed empirically while testing this: `shutil.rmtree()` alone
cannot remove a git checkout's object files on Windows (git marks blobs read-only) — raised a real
`PermissionError` in `tests/test_ocean_dev.py`'s rollback test on first run. Fixed with a shared
`force_rmtree()` helper (clears the read-only bit on every entry first) used by both the module and
skill removal paths.

**`tools/ocean_dev.py` — the entry point, and a real run against this host's actual Ring 1 data.**
Composes `resolve_bundles.py`'s tested functions directly (not a wrapper around its `main()`), so a
failed Verify still stops the run before any Fetch/Place/Activate, exit code 2, unchanged from
Durchgang 1. Dry-run is the default; `--apply` is required for any write; every write `--apply`
performs is recorded to an activation log (`<workspace>/ocean-dev.activation-log.json`), and
`--rollback <that file>` undoes exactly those entries in reverse order.

Real run, ring 1, this host, 2026-08-18 (`--bundles-root` pointed at the local `bundles` checkout):

```
Verify: 5 bundle(s), all_ok=True   (all 5 ring-1 bundles)
Fetch+Place (14 module component(s)):
  13x present, 1x no-catalog-entry (module:memory-hooker — the pre-existing
  catalog/registry naming drift Durchgang 1 already surfaced, not new)
Activate (9 skill component(s)), target=C:\Users\User\ocean-dev\skills:
  dry-run: 9x planned
  --apply: 9x activated (real SKILL.md + assets copied from the real skills
    registry into the sandbox), activation log written with all 9 entries
  --rollback: 9x rolled-back, sandbox emptied, exit 0
  Verified before and after: the real ~/.claude/skills/ (134 entries) was
  never touched by any of the above — checked by directory listing, not
  assumed.
```

This is real evidence, not a synthetic-fixture claim: the write and rollback mechanics for skills
were exercised end-to-end against this host's actual bundle/catalog/registry data, landing in and
cleanly leaving a sandbox, with the live directory checked untouched both before and after.

Test suite after this pass: **82 tests, all green**
(`python -m unittest discover -s tests`; 43 from Durchgang 1 + 20 in
`tests/test_fetch_place.py` + 11 added to `tests/test_host_adapters.py` + 9 in
`tests/test_ocean_dev.py`, one of which uses a real disposable git repository).

**Left for a later pass, named rather than silently skipped:** the general choice-applier
(min/max cardinality) and a `--host` value other than `claude-code` remain out of scope, same
reasons as Durchgang 1 Sec. 3.3; the `no-catalog-entry` finding for `memory-hooker` is unchanged
and still not silently patched here.

### 3.5 Full Dev composition — 2026-08-28

The product direction now distinguishes two compositions without duplicating their authorities:

- **OCEAN Full Dev** is the local development/test composition. It consumes every functional
  `bundle_ref` already declared by the external `ellmos-development-fullsystem/system.v1.json`.
- **OPEN OCEAN** remains the separately gated 13-bundle, public-allowlisted composition declared
  by this repository's skeleton.
- OCEAN is the successor/new BACH. Most extraction is already complete; current BACH work replaces
  legacy internals with the same canonical modules and bundles OCEAN consumes. A BACH-only
  extraction is exceptional and value-gated. LTS, freeze, or archive is a later explicit product
  decision, not an automatic stage transition.

This pass added the smallest executable seam needed for that distinction:

- `resolve_bundles.py` and `ocean_dev.py` accept `--system-manifest <system.v1.json>`. A system
  composition selects all of its `bundle_refs[]`; numbered rings are rejected rather than silently
  truncating Full Dev.
- `--skeleton` and `--system-manifest` are mutually exclusive. System inputs must declare
  `schema: ellmos.system.v1`, a non-empty `id`, and `authority.runtime_authority: false`.
- Bundle lookup accepts either the public export layout
  `manifests/bundles/<id>/bundle.v1.json` or the canonical private projection layout
  `bundles/<id>/bundle.v1.json`. If both exist for one ID, resolution fails closed as ambiguous.
- Hash semantics are unchanged: self-consistency and the composition pin must both match before
  component resolution or any write-capable phase can start. No recipe or system manifest is
  copied into this repository.

**Live Full Dev dry-run, 2026-08-28:** FileCommander executed the pipeline against the canonical
OneDrive projections. All **30/30** referenced bundle manifests were found and internally
self-consistent; **27/30** matched the Full Dev manifest pins. The run returned exit 2 before
Fetch/Place/Activate on exactly these three stale pins:

- `ellmos-core-discovery-bundle`
- `ellmos-agent-orchestration-bundle`
- `ellmos-dev-lifecycle-bundle`

The requested dry-run workspace remained absent, proving the gate stopped before writes. The
portable suite now contains **110 tests, all green**. This is measured progress, not a Full Dev
installation claim: the three stale pins must be reconciled in their canonical recipe/system
authority and then re-read before component breadth can be evaluated.

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

## 5. Stage record and adaptive work packages

Stages 1 and 2 below are completed historical build records. From 2026-08-28 onward there is no
fixed domain or cluster order. The next module/bundle is selected from current evidence after the
knowledge and policy ritual; only the gates *inside* a cycle are ordered: authority and baseline →
test-first cutover → focused tests → full regression → documentation/language parity → commit and
push → separately authorised release decision. A failed cycle is repaired or rolled back before a
different cutover is presented as complete.

### Stage 1 — minimal installable ocean-dev core

- [x] **Resolve + Verify** (`tools/resolve_bundles.py`) — Durchgang 1, this document, Sec. 3.1.
- [x] **Read-only Activate check** (`tools/host_adapters.py`) — Durchgang 1, Sec. 3.2.
- [x] **Fetch + Place for `module:` components not yet locally present** (`tools/fetch_place.py`) —
  Durchgang 2, Sec. 3.4. Source-type dispatch built as planned; the pilot installer's `install_module`
  pattern was ported, its silent-default-branch-fallback bug was not — see Sec. 3.4 for how that was
  proven, not just claimed.
- [x] **Write-side Activate + Roll back**, Claude Code first (`tools/host_adapters.py`, extended) —
  Durchgang 2, Sec. 3.4. Built together in the same pass, per `INSTALLER-TARGET.md`'s ordering.
- [x] **Single-command "ocean-dev up" entry point** (`tools/ocean_dev.py`) — chains Resolve → Verify →
  Fetch/Place → Activate for a chosen ring, dry-run by default, `--apply` required for any write.
  Durchgang 2, Sec. 3.4.
- **Definition of done for this stage — status: partially met, precisely (updated 2026-08-19).**
  Running the entry point against ring 1 on *this* host reaches full activation of every resolvable
  ring-1 skill (proven above, Sec. 3.4, against a sandboxed target — not the live
  `~/.claude/skills/`, by design). The *second-host* half of this DoD now has real `--apply`
  evidence, not just a dry-run: a fresh run on the Mac Studio (Sec. 5, Stage 2, 2026-08-19)
  reached full Activate + Rollback of all 9 ring-1 skills with real registry data (actual
  `SKILL.md` + language variants + assets copied, then removed byte-for-byte on rollback),
  verified never touching the Mac's real `~/.claude/skills` (mtime and entry count identical
  before and after). What did **not** happen, and is not claimed: a real Fetch of any
  `module:` component — every one of the 14 ring-1 modules resolved `unfetchable-source-type`,
  `unpinnable`, or `no-catalog-entry`, none `failed`, because `modules.catalog.json`'s `version`
  field is semver, not a 40-hex commit SHA, for every git-repository module (true on both hosts,
  confirmed against the same freshly-transferred catalog — a data gap, not a Fetch bug). "A
  second host fully installed" therefore stays **not fully met**: Activate/Rollback are proven,
  module Fetch is honestly blocked on catalog SHA-pinning, named as the concrete next step below
  rather than worked around. **Superseded in part, later the same day:** the catalog gained a
  `commit_sha` field and `fetch_place.py` was updated to read it — see Stage 2's "Continued
  2026-08-19 (later the same day)" entry below. 1 of these 14 modules (`WikiStub-Seed`) is now
  pinnable. **Fully closed, same day, final entry:** a real `git fetch` at that pin was executed
  and independently verified (checked-out `HEAD` matches the pin, real GitHub commit history,
  expected files present) — see Stage 2's "final proof for this chain" entry. Fetch/Place is no
  longer proven only by resolution logic or disposable-repo tests for this module.

### Stage 2 — foreign-host smoke (Mac Studio)

**Attempted 2026-08-18, after `T-20260818-179999731`'s OneDrive-sync blocker was reported repaired
(dead sync-engine child process restarted, ~3 min latency verified). Result: suite green, dry-run
completed, one real cross-platform bug found and fixed, one data-freshness caveat found and NOT
worked around.**

- **Access.** No `gh auth`, no GitHub SSH host-key trust yet on that host (`ssh -T git@github.com`
  failed at host-key verification, not credentials) — went straight to the pre-authorised fallback
  rather than establishing new trust on a 24/7 production host mid-task: `git archive` of this
  repository's HEAD (`ecf75fa`) and of the `bundles` checkout, both transferred by `scp` into
  `~/compute/open-ocean-smoke/` and `~/compute/bundles-smoke/` (kept there, not deleted, per the
  task's own instruction; ~2.7 MB combined, no background process left running — checked via `ps
  aux` against the host's pre-existing 24/7 services, none of which are this task's).
- **Test suite — a real bug was caught, not just a clean pass.** First run: **80/82, 2 failures**,
  both `AssertionError: True is not false` on "a failed fetch must not leave a directory behind" /
  the matching `ocean_dev.py` rollback test. Root cause: `force_rmtree()`'s Windows fix
  (chmod every entry to `stat.S_IWRITE`, 0o200, before removing) is wrong on POSIX — a directory
  with mode 0o200 has neither read nor execute, so `shutil.rmtree` can no longer descend into it
  and `ignore_errors=True` swallowed the failure silently, leaving a `.git` directory behind on
  both the fetch-cleanup and the rollback path. **This is exactly the failure class Stage 2 exists
  to catch** — a Windows-only dev host cannot see a POSIX permission-bit bug. Fixed
  (`tools/fetch_place.py::force_rmtree`, full `chmod(0o700)` instead of write-only), re-verified
  **82/82 green on both hosts** after the fix (Windows first, then re-copied and re-run on the Mac).
- **Dry-run resolve, ring 1, against the Mac's own OneDrive-resolved catalog:** `exit 0`, completed
  without error, wrote nothing (`~/ocean-dev` was not created — the dry-run default held on macOS
  too).
- **Data-freshness caveat, checked rather than assumed — this run does NOT double as a "the sync
  fix worked" verification.** `modules.catalog.json` under the Mac's own `~/OneDrive/...` mtime is
  **2026-08-08, 10.8 days old**, against **2026-08-18 (0.7 days)** for the same file on the
  development host — the sync-engine process restart did not (yet, as of this check) pull this
  file's current content across. The two catalogs visibly disagree: `module:memory-hooker`
  resolves `no-catalog-entry` on the fresh laptop catalog and `present` on the Mac's stale one —
  concrete, measured evidence of exactly the risk this document flagged before attempting the
  smoke ("would prove nothing except that the catalog was stale"). The dry-run's specific
  module/skill counts on the Mac are therefore **not** a current inventory of that host and are not
  reported as one; what the run *does* prove — the CLI runs correctly end-to-end on a second OS/
  Python installation with real repository data — stands on its own regardless of catalog age.
- **Left open at the time, named rather than silently dropped:** the Mac's OneDrive catalog
  staleness is a separate, pre-existing sync issue (not an ocean-dev defect) and is not this
  repository's to fix; a future pass that needs a *current* Mac-side inventory should re-check
  this file's mtime first. (Closed below by not using that catalog at all.)

**Continued 2026-08-19 — real `--apply` + `--rollback`, fresh input data (different worker,
taking over from `sovereign2` who continued on a different package). Closes the two gaps the
2026-08-18 smoke left open: the stale-catalog risk and the untested `--apply` path.**

- **Fresh input data transferred, not the Mac's own OneDrive catalog.** Per the caveat above (Mac
  catalog 10.8 days stale on 2026-08-18), this pass did not reuse it. Everything transferred by
  `scp` into a new, separate work directory (`~/compute/open-ocean-sluice/`; the prior pass's
  `open-ocean-smoke/`/`bundles-smoke/` left untouched, per the standing instruction that
  `~/compute/` clones may remain):
  - This repository's HEAD as a fresh `git archive` tarball (commits `ecf75fa` + `05c2f02`, i.e.
    both Durchgang-2 commits including the `force_rmtree` POSIX fix the prior smoke motivated —
    verified present in the extracted tree by grepping the fix's own code comment, not assumed
    from the tarball's stated ref).
  - A fresh `bundles` checkout (`git archive HEAD` of `C:\_Local_DEV\repos\bundles`, commit
    `4b8cb0d`).
  - `modules.catalog.json` (development host, `.TOPICS/.AI/.MODULES/`, 82 364 B, 2026-08-18
    23:18) and the skills registry `components.json` (`.TOPICS/.AI/.SKILLS/registry/`, 93 370 B)
    — both current on the development host.
  - Only the **9 ring-1 skill source directories** the registry itself resolves to (not the full
    487-`SKILL.md`/105 MB tree) — real directories with real content (multi-language
    `SKILL.*.md` variants, `banner.png` assets, etc.), because Activate's `shutil.copytree` needs
    an actual source directory on disk, not just a registry entry.
  - All three tarballs `sha256sum -c`-verified intact on arrival (all `OK`) before extraction.
- **Test suite, re-run from this fresh tree:** `82/82`, `exit 0`
  (`python3 -m unittest discover -s tests`) — same result as the 2026-08-18 smoke's post-fix run,
  now from an independently transferred tree rather than a re-copy.
- **Resolve+Verify, ring 1, against the fresh catalog+registry:** `5/5` bundles `all_ok=True`;
  `9/9` ring-1 skills `resolved`; all 14 ring-1 modules `unresolved` (correctly — the Mac has none
  of the underlying module clones, and this pass deliberately did not fabricate any local
  presence to make Resolve look greener).
- **`ocean_dev.py` dry-run, ring 1:** `exit 0`. Fetch/Place reported, per module: 10×
  `unfetchable-source-type`, 3× `unpinnable`, 1× `no-catalog-entry` — zero `failed`. Activate
  reported 9× `planned`.
- **`ocean_dev.py --apply`, ring 1, explicit sandboxed `--workspace`/`--skills-dir` under
  `~/compute/open-ocean-sluice/workspace/`** (never the default `~/ocean-dev`, and never the live
  `~/.claude/skills`): `exit 0`. Fetch/Place outcomes unchanged from the dry-run (same
  non-`failed` statuses — correct, Fetch never had a pinnable SHA to act on regardless of
  `--apply`). **Activate: all 9/9 ring-1 skills `activated`**, real files landed on disk (checked
  by hand for `decide`: `SKILL.md` + 6 language variants + `banner.png` present). The written
  `ocean-dev.activation-log.json` recorded all 9 entries with exact `dest` paths.
  - **Live `~/.claude/skills` verified untouched on macOS, not just assumed:** captured before
    (`May 24 14:01:24 2026` mtime, empty — 3 `ls -la` lines) and after `--apply` (identical mtime,
    identical entry count). The sandbox guarantee from Sec. 3.2/3.4 (`host_adapters.py`'s
    constructor never defaulting to a live directory) holds on macOS exactly as on Windows.
- **`ocean_dev.py --rollback`, using the just-written activation log:** `exit 0`. All 9 skills
  rolled back in exact reverse activation order (`model-strategy` … `agents-bridge`), sandbox
  `skills/` back to empty. Live `~/.claude/skills` still untouched throughout (checked a third
  time, same mtime/count).
- **Exit-code mechanics confirmed by reading the source, not guessed beforehand:**
  `ocean_dev.py`'s exit 4 ("at least one Fetch or Activate action failed") is driven strictly by
  `FetchOutcome.action == "failed"` / an activate outcome's `action == "failed"` —
  `unpinnable`, `no-catalog-entry`, and `unfetchable-source-type` are none of those; they are
  honestly-reported non-failure outcomes, not swallowed errors. Verified in
  `tools/fetch_place.py::plan_and_fetch()` and `tools/ocean_dev.py`'s `any_failed` computation
  before relying on it — matches this run's own `exit 0` at every step.
- **Housekeeping:** no lingering background processes after the session (`ps aux` checked,
  clean). `~/compute/open-ocean-sluice/` (~19 MB), plus the untouched prior
  `open-ocean-smoke/`/`bundles-smoke/`, left in place per the task's own instruction (all under
  the Mac's `~/compute/`, never its OneDrive path). Logs pulled back to the development host
  (checksum-verified tarballs plus every `ocean_dev.py --report`/stdout log); not committed into
  this repository as raw files — the evidence convention here is the inline excerpts above,
  matching this section's own established style.
- **What this run does and does not close:** "Second host fully installed" (Stage 1's DoD) is now
  split cleanly rather than left as one unproven claim: the **Activate/Rollback half is proven**
  with real data on a second OS; the **Fetch half is correctly blocked by a data gap** — every
  git-repository module in `modules.catalog.json` carries a semver `version`, not a commit SHA,
  true on both hosts, not a Mac-specific finding. Making Fetch succeed for real needs the catalog
  to carry actual commit SHAs for at least the 14 ring-1 modules; that is a
  `.MODULES/modules.catalog.json` data-entry task, not an `open-ocean` code task, and is named
  here as the concrete next step rather than being worked around (no synthetic SHA was written
  into the transferred catalog).

**Continued 2026-08-19 (later the same day) — the data side was delivered, `fetch_place.py` was
not yet reading it.** `.MODULES/_scripts/build_catalog.py` gained a separate, builder-computed
`commit_sha` field (13/22 current git-repository modules pinned, including Ring 1's
WikiStub-Seed: `3476ba2c2c0ef76c4988f035b9dc7a7f12458af4`), reviewed and accepted (41/41 tests).
But `fetch_place.py::resolve_pin_for_module()` still only read `version` — the new field's effect
on Fetch was null until this pass. Decision (team lead, technical): `resolve_pin_for_module()`
prefers `commit_sha`, falling back to `version` only when `version` itself is already a full
40-hex SHA (the pre-existing behaviour, kept unchanged for older/synthetic data) — `version`
stays the human-facing semver field, `commit_sha` is the one actual pin, no doubled meaning
between the two, and still no silent branch fallback either way.

- **Code change:** `tools/fetch_place.py::resolve_pin_for_module()` (prefer `commit_sha`,
  SHA-shaped-`version` fallback), the `unpinnable` outcome in `plan_and_fetch()` (now reports
  both `raw_version` and `raw_commit_sha` in its detail, so a human sees that both fields were
  checked), the `unpinnable` action's description string, and the module's own "Scope" docstring
  (previously claimed "no SHA pins at all", now dated and corrected).
- **Tests:** 8 new (`ResolvePinForModuleTests`: commit_sha preferred over semver version,
  commit_sha preferred over an already-SHA-shaped version too, missing/malformed commit_sha falls
  back to a SHA-shaped version, both fields non-SHA or missing stay unpinnable;
  `PlanAndFetchTests`: a real catalog-shaped entry with `commit_sha` set is `planned` in dry-run
  using that SHA, the `unpinnable` outcome carries both raw fields). **90/90 total**, up from 82 —
  all pre-existing tests unchanged and still green.
- **Local verification against the real, current catalog** (not a fixture) — the three ring-1
  git-repository modules, with their Resolve status manually set to `unresolved`/
  `present_locally: False` the way a foreign host without local clones would see them (on *this*
  dev host they resolve `present`, which masks Fetch's pin logic entirely — the same masking
  effect Sec. 3.4 already documented, so this had to be forced rather than observed from a plain
  dry-run here):
  ```
  module:WikiStub-Seed             -> planned    sha=3476ba2c2c0ef76c4988f035b9dc7a7f12458af4
  module:build-your-users-mind     -> unpinnable raw_version=1.1.0-dev  raw_commit_sha=null
  module:project-docs-template     -> unpinnable raw_version=0.1.0      raw_commit_sha=null
  ```
  Before this fix, all three were `unpinnable`. After: WikiStub-Seed is pinnable (1/3 → uses the
  real `commit_sha`), the other two remain correctly `unpinnable` with both raw fields visible as
  the reason — the catalog itself does not pin them, this was never a code bug in the two
  remaining cases.
- **Mac re-test deliberately not repeated.** The change is host-independent: pure catalog-field
  lookup logic plus data already verified identical between hosts in the prior continuation (the
  transferred catalog *is* a copy of the same file); no OS-specific code path changed. Recorded
  here as a conscious decision, not an oversight — the Stage 2 foreign-host DoD (Activate/Rollback
  on macOS with real data) was already proven separately and does not need re-proving for a change
  that never touched Activate, Rollback, or any platform-specific path (`force_rmtree` etc.).
- **What is still open:** 9/22 catalog-wide git-repository modules (including 2 of Ring 1's 3)
  remain unpinned by the catalog's own data — a data-entry task for whoever owns those modules'
  release process, not further `open-ocean` code work.

**Continued 2026-08-19 (final proof for this chain) — a real `git fetch` at the pin, not just
resolution logic.** Everything above proved that `WikiStub-Seed` *resolves* as pinnable; this step
proves Fetch actually *works* end to end, using `fetch_place.py`'s own tested `plan_and_fetch()`
(the real production code path, not a re-implementation) with `apply=True` against a disposable
sandbox — never the canonical clone, never OneDrive (`%TEMP%\...\scratchpad\
wikistub_real_fetch_proof\`, a component with Resolve status forced to `unresolved` the same way
the earlier verification did, since local presence otherwise short-circuits Fetch before it ever
runs).

- **Result:** `action="fetched"` (not `"planned"` — this was a real `--apply`, not a dry-run).
  Reported `head` equalled the pin exactly.
- **Independently re-verified, not just trusting the tool's own report:** `git -C <dest>
  rev-parse HEAD` → `3476ba2c2c0ef76c4988f035b9dc7a7f12458af4`, matching the catalog's pin
  character-for-character. `git log -1` showed real GitHub history (a genuine merged pull
  request, dated 2026-07-31 — not a synthetic/local throwaway repo this time, unlike the disposable
  fixtures `tests/test_fetch_place.py` uses for its own git tests). The expected working-copy
  content was present and readable (`md_to_json.py`, `language_model.py`,
  `wikistub_seed_cli.py`, etc. — the same files this ticket's earlier WikiStub-Aufbauprojekt work
  forked from this exact upstream project).
- **No auth/URL problem encountered** — `WikiStub-Seed` is `"visibility": "public"` in the
  catalog and the GitHub repo is public, so an anonymous HTTPS clone worked without credentials.
  (Had it failed, the instruction was to document the precise failure point rather than work
  around it; that branch was not needed here.)
- **Sandbox cleaned up afterward** (~9.4 MB removed) rather than kept as a standing artifact —
  it was a one-shot proof of a code path already covered by the test suite's own disposable-repo
  tests, not new information worth preserving on disk; this paragraph is the durable record
  instead.
- **This closes the Fetch/Place half of Stage 1's "second host fully installed" DoD for the one
  module the catalog currently pins in Ring 1.** Combined with the earlier-proven Activate/Rollback
  half (Mac Studio, 2026-08-19) and this same day's resolution-logic fix, all four
  Resolve→Verify→Fetch/Place→Activate steps (plus Rollback) now have at least one real,
  independently-verified run each against real data — Fetch/Place specifically was, until this
  step, the one step proven only by disposable-repo tests and resolution-logic checks, never by an
  actual fetch of a real, cataloged module. The remaining gap is data breadth, not proof-of-concept:
  9/22 catalog-wide modules (2 of Ring 1's 3) still lack a pin because their own clones are not
  clean+pushed, not because Fetch cannot fetch them once they are.

**Continued 2026-08-20 — the combined foreign-host transaction is now proven in one invocation.**
The previous entries proved Fetch/Place and Activate/Rollback separately. This continuation ran
the actual `tools/ocean_dev.py --apply` chain once on the Mac Studio with both kinds of writable
work present, then used the resulting single activation log for one rollback.

- **Pinned inputs and transport:** the source snapshots came from `open-ocean`
  `00bcd261981b335854812941c00be867368efc89` and `bundles`
  `e25bbd1a17870b2c2bb2d07ebe223027c8588b74`. The Mac independently matched the transported
  archive SHA-256 values: `064D2728…DB7ED14E` (open-ocean), `D68ADB80…B4C1BB31` (bundles), and
  `8AECE389…B4C3367` (the nine real skill inputs).
- **Foreign-host baseline:** the portable test suite ran on macOS immediately before apply:
  **90/90 passed**.
- **One apply:** all 5 Ring-1 bundle hashes verified; `module:WikiStub-Seed` was fetched and its
  independent checked-out `HEAD` matched the catalogue pin
  `3476ba2c2c0ef76c4988f035b9dc7a7f12458af4`; all 9 Ring-1 skills were activated into the
  explicitly supplied sandbox. The same report classified the remaining module work honestly:
  2 `unpinnable`, 10 `unfetchable-source-type`, 1 `no-catalog-entry`, and 0 failed actions.
- **One transaction, one rollback:** the activation log contained exactly 10 entries — the fetched
  module and 9 skills. One `--rollback` removed that module and every sandbox skill; no sandbox
  skill remained.
- **Live-target isolation:** independent snapshots of the real `~/.claude/skills` tree before
  apply, after apply and after rollback had the identical SHA-256
  `46436EF2…498E133`. The live target was never used as the activation destination.
- **Process and evidence readback:** an independent SSH process check after the invoking session
  had exited found no remaining ocean-dev/fetch process. The retained evidence lives under the
  bounded remote work directory
  `~/compute/open-ocean-sluice-combined-20260820T2350B-ASUS-GEI/`; its pulled `summary.json` has
  SHA-256 `398C0664…8BB6A5B`.
- **Claim boundary:** this closes the formerly untried combined mechanism path, not PRIVATE.txt
  release condition 2. The destination was a sandbox, only one Ring-1 Git module was fetchable at
  a safe catalogue pin, and the invocation did not construct a complete working ocean runtime.
  Stage 3 remains separately gated and untouched.

### Stage 3 — adaptive BACH/OCEAN module and bundle cycles

- The earlier fixed Cluster 9 → 1 → 3 → 5 → 7 → 4 → 6 → 8 → 2 sequence is historical guidance,
  **not a binding execution order**. The explicit 2026-08-28 product decision supersedes it.
- At the start of every new section, lift current knowledge through `.AI`, Gardener, the policy
  registry, and directly applicable policy binders. Classify evidence as current, historical,
  conflicting, or unavailable before choosing the next bounded cycle.
- Selection is evidence-driven: readiness, dependency leverage, testability, risk, an active
  blocker, or a newly discovered high-value BACH unique may make any eligible module/bundle next.
  A BACH unique is extracted only as an exceptional, separately justified action.
- Each cycle wires one module or bundle into BACH and/or OCEAN, disconnects only the superseded
  legacy path, proves equivalence with shared anonymized fixtures where applicable, and keeps root,
  help, roadmap/changelog, task, and DE/EN documentation deltas in the same commit.
- `tools/check_k9_data_contract.py` remains a useful fixture-equivalence pattern, not a command to
  start with Cluster 9 regardless of evidence. BACH and OCEAN consume the same canonical modules;
  the main development direction is FULL OCEAN development while OPEN OCEAN remains separately
  allowlisted and release-gated.

## 6. Honesty check — what this plan is not claiming

- Ring 1 is **resolvable, verifiable, fetchable where safely pinned, and activatable**. All six
  installer steps have code and real-data proof. Updated 2026-08-20: one Mac Studio `--apply`
  invocation combined the real SHA-pinned Fetch/Place of `WikiStub-Seed` with activation of all 9
  Ring-1 skills, and its single log rolled back all 10 writes. The former combined-path gap is
  therefore closed. The remaining limit is breadth, not the transaction mechanism: the other 2
  Ring-1 Git modules (`build-your-users-mind`, `project-docs-template`) remain correctly
  unpinnable because the catalogue does not pin them, 9/22 Git modules catalogue-wide are in the
  same state, ten Ring-1 module references are local-directory sources rather than fetch targets,
  and one reference still has no catalogue entry. The foreign-host proof used a sandbox and did
  not create a complete working ocean runtime.
- Nothing here lifts `PRIVATE.txt`. Conditions 2 and 3 both still read "not met" honestly; the
  combined integration proof advances the installer evidence without claiming that either release
  condition is satisfied.
- `memory-hooker`/`memoryhooker` and `software:MediaBrain` (an unhandled component kind, surfaced
  when running `--ring all`) are real, live findings from running the tool against real data, kept
  as findings rather than quietly patched around, because patching the catalog or adding a
  `software_app` resolver were not asked for in this pass and are better done deliberately.

## 7. OCEAN-first execution checkpoint — 2026-08-29

The product direction is now explicit: the legacy BACH migration plan is delegated to BACH's own
task system; this repository's active implementation focus is a usable OCEAN. The private Full Dev
composition may consume private modules, while OPEN OCEAN remains separately allowlisted and
publication-gated. The runtime is selected by the declared `runtime.host` capability so today's
private provider does not become a hard dependency of the future public product.

### Delivered in this cycle

- `ocean.py` is the product entry point for `plan`, `up`, `status`, `down`, and `user add`.
- The existing `ocean_dev.py` remains the sole Resolve → Verify → Fetch/Place → Activate/Rollback
  transaction boundary; the new lifecycle layer does not duplicate the installer.
- One local runtime instance is supervised through a loopback-only authenticated control channel.
  Its web health is checked live before `up` succeeds, and `down` targets only that exact instance.
- User creation delegates to the selected runtime. Passwords cross only a hidden prompt or stdin
  pipe and never appear in command-line arguments.
- The runtime receives a generated local secret with reload disabled. A start → stop → restart
  regression test covers both the former orphan-child defect and stale-state restart race.

### Current evidence

- Portable suite: **126 passed**.
- Applied Windows Full Dev snapshot: **29/29 then-declared bundle pins verified**, **52 modules
  resolved**, **62 skills resolved and present**, live root page **HTTP 200**, live health
  **HTTP 200**, database check green with 20 tables.
- Lifecycle proof: start → live status → controlled stop with port release → restart → live health.
- Real user-bootstrap proof: a random disposable administrator was created through `ocean user
  add`, its stored password hash verified, and the exact row removed; user count was 0 before and
  after the acceptance run.
- Honest boundary: 25 module references are unresolved and nine of them are required by the applied
  Full Dev snapshot (`audit-trail`, `automation-registry`, `automation-runtime`, `billing`,
  `entitlement-enforcement`, `hosted-operations`, `runtime-boundary-enforcement`,
  `sso-rbac`, `tenant-isolation`). The machine report therefore says `full_composition: false`.

### Adaptive next-cycle rule

No fixed module order is imposed. Before the next bounded section, repeat the knowledge-lift ritual
through `.AI`, Gardener and applicable policy binders, then choose from the measured result. The
next cycle should either (a) close the highest-leverage genuinely required module gap or (b) correct
the Full Dev manifest if a listed commercial/public concern is misclassified as required. Each
cycle must keep runtime acceptance, rollback/stop evidence, root help, changelog and DE/EN
documentation in the same tested commit. Public release, tags, visibility and `PRIVATE.txt` remain
separate explicit gates.

Language work follows the same cycle rather than a later translation batch. English is the
repository documentation authority and German is maintained section-for-section in parallel; code
blocks, identifiers, counts and limitation statements stay invariant. For product surfaces, each
integration uses the selected runtime's existing locale mechanism and updates every already
supported locale for any new end-user string. OCEAN must not introduce a second translation system
beside the runtime provider's catalog. A locale is counted as covered only after the real surface,
not just its resource file, has been checked.

## 8. Adaptive provider cycle 1: software endpoint registry — 2026-08-29

The first module cycle followed the adaptive rule above rather than a predeclared sequence. The
section-start knowledge lift re-read the live `.AI` module/skill sources, Gardener and applicable
policy authority before selecting a required gap. The module catalog remained structurally valid
at 68 entries. OneDrive resynchronisation changed source-file hashes, but rewriting the canonical
development-system bindings would have invalidated historic evidence through a broad hash cascade;
that authority was therefore left unchanged for a separate, explicit migration.

### Contract and implementation

- `architecture/ocean-full-dev.component-bindings.v1.json` is a content-hashed integration overlay,
  explicitly marked `runtime_authority: false`. It does not replace recipe or catalog authority.
- The exact ref `module:software-endpoint-registry` is bound to catalog entry `system-explorer`,
  repository `https://github.com/ellmos-ai/system-explorer.git`, commit
  `ec50c92319ba8fc262d695b86818fc85666feff7`, placement `software-endpoint-registry`, provider
  manifest `ellmos-module.v2.json`, and capability `software.endpoint.registry`.
- Bound refs deliberately bypass fuzzy and case-folded alias matching. Resolution fails closed on
  an invalid overlay hash, a repository mismatch, a non-full commit SHA, unsafe placement, wrong
  Git HEAD, dirty checkout, wrong origin, wrong provider identity, or missing required capability.
- Fetch/Place never overwrites a wrong existing placement. A correct placement is reported as
  `present-pinned-provider`; a new exact checkout is reported as `fetched` only after provider
  verification.
- The activation log is now an append-preserving rollback ledger. Existing entries are validated
  before any write, exact duplicate additions are idempotent, and malformed or conflicting entries
  fail before activation.

### Live acceptance evidence

- The real Full Dev plan applied the overlay to exactly one ref while retaining all **29/29** valid
  bundle pins. Required missing components fell from **10 to 9**; resolved modules rose from
  **51 to 52** and unresolved module refs fell from **26 to 25**.
- The provider placement has the exact pinned HEAD and expected Git origin. Its module manifest has
  provider ID `system-explorer` and declares `software.endpoint.registry`.
- A real `software-endpoints --refresh` run against a temporary OCEAN resource produced one
  installed software record with two endpoints, one CLI and one HTTP. The temporary fixture was
  then removed recoverably.
- `ocean up --apply` returned a running `ellmos-core`; `/api/health` and `/` both returned HTTP 200,
  and the runtime database check retained its 20-table result.
- The rollback ledger grew from **62 skill entries to 63 total entries** (62 skills plus the bound
  module), proving that the module cycle did not erase prior rollback information.
- The paired English/German README and changelog, root CLI help, architecture plan and portable
  suite were updated in the same cycle. The final portable suite is **126 passed**.

### Post-sync authority gate

After OneDrive resumed, the live `ellmos-development-fullsystem` authority advanced from the 29-ref
snapshot used by the successful apply to **30 bundle refs**, adding `ellmos-therapy-bundle` and
updating several pins. A fresh read-only OCEAN plan was therefore run again instead of assuming the
installed snapshot still represented current source authority.

- Against the current canonical OneDrive `.BUNDLES` projection, all 30 manifests are internally
  self-consistent and **27/30** match the live system pins. The three mismatches are
  `ellmos-core-discovery-bundle`, `ellmos-agent-orchestration-bundle`, and
  `ellmos-dev-lifecycle-bundle`.
- The older local recipe worktree is not a valid fallback: only **24/30** current refs verify there;
  five use older valid hashes and the newly selected therapy manifest is absent at the expected
  exported path.
- OCEAN stopped before Resolve, Fetch/Place, Activate or runtime replacement, exactly as the
  fail-closed verification contract requires. The existing installed snapshot remains running and
  healthy at `http://127.0.0.1:8800`; its root and health endpoint still return HTTP 200, its DB
  check still reports 20 tables, and the bound provider remains clean at the exact commit.

The three authoritative pin mismatches must be reconciled in the recipe/system authority and then
re-read through the section-start knowledge lift. OCEAN must not hide them with an ad-hoc local
repin or a copied system manifest.

This finishes the first usable OCEAN module integration, not the Full Dev composition or Public
OCEAN release. The remaining required gaps are `audit-trail`, `automation-registry`,
`automation-runtime`, `billing`, `entitlement-enforcement`, `hosted-operations`,
`runtime-boundary-enforcement`, `sso-rbac`, and `tenant-isolation`. The next cycle repeats the
knowledge lift and chooses among those live findings. No tag, release, merge, visibility change or
`PRIVATE.txt` change belongs to this cycle.

## 9. Product-surface correction and installed-snapshot recovery — 2026-08-29

This corrective section was selected by direct user-visible evidence, not by the remaining-module
list: the address previously reported as OCEAN showed TerminPilot's offline page after the runtime
process disappeared and showed TerminPilot's scheduling UI again when the provider was restarted.
The earlier acceptance had asserted only HTTP 200 and a login-capable page. It had not asserted the
identity of the product shown there, so that part of the evidence is withdrawn.

### Section-start knowledge lift

- **Current:** the installed transaction records both resolved `ellmos-core` capabilities and the
  resolved optional `ellmos-unified-gui` provider with `operator.ui` and `unified-gui.host`. The
  provider's own contract mounts that UI only when `ELLMOS_CORE_CONSOLE_ENABLED=1`; the prior OCEAN
  runtime specification did not set the opt-in.
- **Current:** the direct live response at the old port exposed a TerminPilot PWA manifest,
  scheduling copy and a root-scoped service worker. When no process listened on port `8800`, that
  worker could still render the cached TerminPilot offline shell.
- **Historical/mixed:** Gardener returned OCEAN, TerminPilot and unified-GUI observations from
  tickets, memories and transcripts, but its local checkout was two commits behind and the hits did
  not establish newer runtime authority. They were treated as orientation only.
- **Unavailable:** the federated ControlCenter governance query returned aggregate `UNKNOWN`, with
  both decisions and policy registry unconfigured. No policy decision was inferred from that
  absence. The applicable module release policy still leaves tags, publication and visibility out
  of this private corrective cycle.

### Corrected contract

- A resolved `unified-gui.host` now selects exactly one OCEAN operator surface. OCEAN enables the
  provider's console mount, writes only an OCEAN-owned workspace title override, and returns
  `/control/` rather than treating the provider's domain root as the product.
- New installs use dedicated default port `8810`. This gives OCEAN a different browser origin from
  the provider's standalone TerminPilot PWA on port `8800`. At this checkpoint, however, the same
  provider process still exposed its own root, manifest and root-scoped worker on the new origin;
  the stronger origin-ownership correction is recorded in section 11.
- `ocean start --workspace <sandbox>` starts the already installed transaction snapshot without
  consulting changed live recipe authority. This is deliberately distinct from `ocean up --apply`:
  the latter remains the transaction/apply boundary and still stops on the three current pin
  mismatches.
- A stale `running` state is recoverable only when its authenticated control channel, recorded
  public runtime endpoint and requested port are all inactive. A live or foreign listener remains a
  fail-closed conflict rather than being killed or overwritten.

### Acceptance evidence

- Portable suite: **128 passed**; Ruff and `compileall` also passed.
- The retained 29-ref installed snapshot restarted without reapplying the now-mismatched 30-ref
  live authority. Live status is `running/ok` at `http://127.0.0.1:8810/control/`; health is HTTP
  200 and the database check still reports 20 tables.
- Direct HTML inspection found `OCEAN Full Dev` and no `TerminPilot`, `Terminkoordination` or
  `Terminabfragen` marker at the returned product URL.
- A fresh Playwright browser loaded the overview with title `OCEAN Full Dev — Übersicht`, then
  navigated to the Skills panel with title `OCEAN Full Dev — Skills`. Port `8800` had no listener.
  This did not yet exercise an installed PWA or a profile retaining a root-scoped worker.
- One pre-existing cosmetic browser finding remains: the mounted UI does not declare a favicon, so
  the browser requests `/favicon.ico` and receives 404. It does not affect navigation, health or
  product identity and is not silently counted as fixed.

At that checkpoint, this correction made the Full Dev surface usable and truthfully identifiable
as OCEAN. It did not close the nine missing required modules, the three live recipe-pin mismatches, BACH parity,
foreign-host full-system proof, OPEN OCEAN, release, tag, visibility or `PRIVATE.txt` gates.

## 10. Adaptive provider cycle 2: recipe reconciliation and automation registry — 2026-08-29

This cycle starts from the measured findings of sections 8 and 9 rather than from a fixed module
order. Its section-start lift re-read the live `.AI` system and module sources, Gardener findings,
the architecture contracts and the visibility policy. The policy keeps Hosted-only concerns
private; it does not allow OCEAN to pretend that billing, tenancy or SSO providers exist. The
module catalogue does, however, contain one exact reusable provider for the required
`automation-registry` gap: `automation-master` declares `automation.registry` at a clean, pushed
commit. `ellmos-scheduler` is not substituted for the separate `automation-runtime` contract.

### Recipe/system authority reconciliation

- The 30-ref system projection combined three independently advanced recipe histories. No single
  existing remote branch contained its current Core, Compare-Race, Dev-Lifecycle and Therapy pins,
  so OCEAN did not hide the mismatch with a copied manifest or local repin.
- A clean reconciliation worktree based on recipe `main` forward-ported Compare-Race and the
  Therapy bundle, restored all Therapy crosswalk/binding records, and propagated the repository's
  own content-hash chain with its generators.
- TDD first proved the missing Therapy ref and Compare-Race member, then the reconciled state proved
  all **30/30** Full Dev pins against their exact bundle manifests. The portable component-registry
  receipt advanced additively to V10; historical receipts were not rewritten.
- The result is pushed as
  `ellmos-development-system@489b67880b42ba4bd2a1d8052239896f84192269` on branch
  `codex/ocean-fullsystem-reconcile-20260829`. It is the pinned integration source for this cycle,
  not yet a claim that canonical recipe `main` has merged it.
- Recipe verification passed its skill/hash generators, README generator, compile check and
  whitespace check. The host-independent suite passed **148 tests, 5 skips and 20 subtests**. The
  unabridged suite additionally stayed fail-closed on an expired WORKSTATION-LG currentness receipt
  and WORKSTATION-LG-only local files; ASUS-GEI did not forge replacements for either host proof.

### Exact provider binding and applied Full Dev state

- The content-hashed OCEAN overlay now binds `module:automation-registry` to catalog entry and
  provider `automation-master`, repository `https://github.com/dev-bricks/automation-master.git`,
  commit `ad40de721615518e409b53b00ed4b2a49840db28`, placement `automation-registry`, provider
  manifest `ellmos-module.v2.json`, and required capability `automation.registry`.
- A behavioral TDD test loads the shipped overlay and proves that this declared ref resolves
  through the exact provider contract; no case-folded or fuzzy alias is accepted.
- The read-only OCEAN plan verified **30/30** pins and planned the exact provider plus **18** Therapy
  skills. After controlled stop/apply/start, live status is `running/ok` at
  `http://127.0.0.1:8810/control/`.
- The installed provider is a clean detached checkout at the exact commit and expected origin. Its
  manifest declares `automation.registry`; the runtime projection includes its `src` path.
- Current resolution is **53 resolved modules**, **24 unresolved module refs**, **80 resolved and
  present skills**, and **8 required gaps**. The append-preserving rollback ledger contains 80
  skill entries and two bound-module entries. Machine truth remains `full_composition: false`.
- HTTP returned UTF-8 OCEAN content with status 200. A real Chromium/Playwright run asserted the
  exact title `OCEAN Full Dev — Übersicht` and navigated the Skills link to `/control/p9`.
- The Open OCEAN suite is **130 passed**; Ruff, `compileall`, whitespace checks and UTF-8 root,
  plan and up help readbacks also passed.

### Late-write lifecycle finding and correction

The first real apply attempt encountered an already running OCEAN instance. The command correctly
refused a second process, but only after Fetch/Activate had updated the sandbox. The resulting state
was valid and was subsequently started through a controlled `down` → `up`, yet the ordering was not
transaction-safe. A red regression reproduced the behavior by introducing a new skill while a
sandbox was live. The runtime/port preflight now runs before `run_transaction` and repeats directly
before process creation to close the race. The green regression proves that a rejected second
`up --apply` neither creates the skill placement nor changes the activation ledger. A repeated
real command against the live port returned the existing-runtime gate while the SHA-256 values of
the activation ledger, install record and generated manifest, the 80-skill directory count, and
the clean provider HEAD all remained unchanged.

### Unordered continuation tasks

The next section is selected only after repeating the `.AI`/Gardener/policy lift. This list is a
pool, not a sequence, and is the task source to migrate into OCEAN Task-Master once that integration
exists:

- provide or deliberately reclassify `audit-trail`;
- provide the distinct `automation-runtime` contract without treating the scheduler as equivalent;
- provide or deliberately reclassify `runtime-boundary-enforcement`;
- keep `billing`, `entitlement-enforcement`, `hosted-operations`, `sso-rbac` and
  `tenant-isolation` private and fail-closed until actual Hosted providers and product authority
  exist;
- merge or otherwise canonically adopt the pushed recipe reconciliation before a public or
  foreign-host release proof;
- derive and test the separate OPEN OCEAN allowlist; Full Dev's private providers must never leak
  into it by default.

Every selected section repeats tests, real runtime/browser acceptance where relevant, root CLI help
readback, paired English/German README and changelog updates, this plan/task pool, commit/push and an
explicit integration checkpoint. An integration tag records evidence; it does not authorize a
public release, repository visibility change or modification of `PRIVATE.txt`.

## 11. Product-owned origin and persistent-PWA correction — 2026-08-29

This corrective cycle interrupts the unordered provider pool because direct user evidence again
showed the installed TerminPilot offline shell where OCEAN was expected. Read-only live inspection
separated two facts: port `8800` had no listener, so its previously installed TerminPilot PWA was
truthfully offline; port `8810/control/` was healthy OCEAN. The boundary was nevertheless still
incomplete because the process on `8810` exposed the runtime provider's root page, appointment-
worded manifest and root-scoped `/sw.js` outside the mounted OCEAN console.

### Corrected origin contract

- When `unified-gui.host` selects the OCEAN operator surface, the lifecycle now starts an
  OCEAN-owned ASGI boundary around the selected `ellmos-core` provider. Lifespan, health and the
  provider API remain delegated; browser identity is no longer delegated.
- `/` returns a non-cacheable redirect to `/control/`. `/manifest.webmanifest` names `OCEAN Full
  Dev` and limits its start URL and scope to `/control/`. `/offline` contains only OCEAN copy.
- `/sw.js` is a non-cacheable retirement worker that deletes legacy `ellmos-core-pwa*` cache
  entries, unregisters itself and refreshes controlled windows. OCEAN HTML also carries a bounded
  cleanup script so a currently controlling legacy root worker is removed without waiting for the
  browser's periodic update.
- Cleanup is limited to the dedicated OCEAN origin's root-scoped service-worker registration and
  provider cache prefix. It does not clear unrelated or future OCEAN caches, issue
  `Clear-Site-Data`, remove cookies, local storage, sessions or the separately installed
  TerminPilot PWA on port `8800`.

### TDD and live evidence

- The red test first failed because `tools.ocean_origin` did not exist and the lifecycle still
  launched the provider CLI directly. Green tests now prove Root redirect, OCEAN manifest and
  offline identity, retiring worker behavior, control-HTML injection, unchanged delegation of
  non-OCEAN provider routes, and selection of the OCEAN runtime entry point.
- The installed snapshot was stopped and restarted without reapplying recipe authority. Its
  runtime specification now launches `tools/ocean_runtime.py`; status is `running/ok` at
  `http://127.0.0.1:8810/control/`.
- Live HTTP proves `307 / -> /control/` with `Cache-Control: no-store`, an OCEAN manifest scoped to
  `/control/`, a retiring worker, and a status-200 overview containing the cleanup marker but no
  `TerminPilot` marker.
- A persistent Chromium profile deliberately received an `ellmos-core-pwa-v1` cache containing
  the old TerminPilot offline text plus an unrelated synthetic future-OCEAN cache. After reload,
  the provider cache was absent, the unrelated cache remained, service-worker registrations were
  zero, Root reached the OCEAN overview and no TerminPilot marker remained. A code-point readback
  confirmed `OCEAN Full Dev — Übersicht` with U+2014 and U+00DC and no replacement character.
- The complete suite is **133 passed**. Ruff, `compileall` and `git diff --check` pass. Paired
  English/German README and changelog entries and this plan were updated in the same cycle.

The checkpoint is `ocean-full-dev-origin-koralle-20260829`. It records the private Full Dev fix;
it is not an OPEN OCEAN release and changes neither repository visibility nor `PRIVATE.txt`.
At that historical checkpoint, eight required module gaps and the separate OPEN OCEAN allowlist
remained open. Section 12 supersedes the current gap count after repeating the section-start
`.AI`/Gardener/policy lift.

## 12. Product boundary and SPEEDBOAT separation — 2026-08-29

This adaptive cycle began with the required section-start lift through
`.AI/SYSTEM-PRODUKTLINIE.md`, `.AI/VISIBILITY-POLICY.md`, `.AI/GLOSSARY.md`,
`.AI/.OS/DECISIONS.md`, Gardener and USMC. The user then ratified the product algebra:

```text
OPEN OCEAN = PUBLIC
PRIVATE OCEAN = PRIVATE_NON_PROPRIETARY
FULL OCEAN = OPEN OCEAN + PRIVATE OCEAN

SPEEDBOAT = PROPRIETARY
            + SELECTED_PUBLIC
            + SELECTED_PRIVATE_NON_PROPRIETARY
```

SPEEDBOAT is an independent sibling stack, not an OCEAN edition, overlay or inherited superset.
It may navigate selected OCEAN waters or travel between islands, but every shared bundle/module
requires an explicit allowlist entry. Repository visibility remains separate from product
membership.

### Declarative boundary and recipe proof

- Recipe commit `7754f811b4b793fa7e25d42c395cf6b31d6eacaa` adds the closed
  `contracts/product-stack-boundary-contract.v1.json` contract and an independent
  `systems/products/speedboat/system.v1.json` manifest with empty inheritance and empty shared
  allowlists.
- FULL OCEAN now declares 28 platform/domain bundles. The proprietary
  `ellmos-multitenancy-bundle` and `ellmos-saas-operations-bundle` are SPEEDBOAT-only and no
  longer create false OCEAN completeness gaps.
- The legacy catalog token `hosted-private` is retained only for schema/hash compatibility and
  maps to product category `proprietary`; this is not a claim that private equals proprietary.
- TDD first failed on the missing product contract/manifest and the stale 30-bundle assumptions.
  The focused recipe suite is now **41 passed, 1 skipped**, and the generated README catalogue is
  in sync. The unabridged recipe suite still fails closed only on the previously reproduced
  external evidence gates: one missing WORKSTATION-LG local file and an expired System Explorer
  currentness receipt (**152 passed, 5 skipped, 1 failed, 14 errors**).

### Controlled apply and live readback

- A read-only plan against the new recipe verified **28/28** exact bundle pins and planned 158
  component occurrences: **53 of 65 module references resolved**, **12 unresolved**, and all
  **80/80 skills resolved**.
- Only `module:automation-runtime` remains a required FULL OCEAN gap. Machine truth therefore
  remains `full_composition: false`; the other unresolved references are optional.
- After a controlled `down` and `up --apply`, install state at
  `C:\_Local_DEV\ocean-full-dev\ocean.install.json` records the applied 28-pin transaction and
  the same single required gap. Runtime status is `running/ok` on port `8810`.
- Live HTTP proves `307 / -> /control/` with `Cache-Control: no-store`; the UTF-8 web manifest
  names `OCEAN Full Dev`, and the control HTML contains no TerminPilot, appointment-coordination
  or appointment-query product markers.
- The complete Open OCEAN suite is **135 passed**; Ruff, `compileall` and whitespace checks pass.
  English/German product-boundary docs, READMEs and changelogs were updated together and retain
  the release/visibility non-claim.

### Unordered continuation pool

The next module/bundle section is selected only after repeating the `.AI`/Gardener/USMC/policy
lift. The pool has no fixed order:

- provide and TDD-integrate the distinct `module:automation-runtime` contract;
- derive and test a default-deny OPEN OCEAN public allowlist independently from FULL OCEAN;
- decide whether/how recipe commit `7754f811…` is adopted into canonical recipe `main`;
- select shared OCEAN components for SPEEDBOAT only when a concrete proprietary use case exists;
- keep BACH-only extraction exceptional and value-gated while BACH consumes the same canonical
  modules as OCEAN;
- repeat runtime/HTTP acceptance, bilingual/root/help/changelog/plan updates, tests,
  commit/push and one named integration checkpoint for each completed section.

The checkpoint name for this private integration cycle is
`ocean-full-dev-wellenkamm-20260829`. It is not an OPEN OCEAN release and authorizes neither a
repository-visibility change nor a modification of `PRIVATE.txt`.

## 13. Automation Runtime integration and declared-composition closure — 2026-08-29

This module cycle repeated the section-start lift through `.AI`, Gardener, USMC and the applicable
release/visibility policies. It retained the ratified product algebra:

```text
OPEN OCEAN + PRIVATE OCEAN = FULL OCEAN
```

The cycle closes the final required component in the private FULL OCEAN development composition;
it does not convert private components into OPEN OCEAN and does not attach SPEEDBOAT inheritance.

### Provider and binding proof

- `automation-master` now provides the separate logical `AutomationRuntime` observer at pushed
  commit `c2de7188626510b181c4ecf2708c15f2395e32aa` on branch
  `feat/automation-runtime-observer-20260829`.
- The provider requires closed authority-resolution inputs, native provider and scheduler
  readback, immutable execution pins for non-app-native runs, SHA-256 input fingerprints, bounded
  redacted summaries and create-only content-hashed receipts outside configured OneDrive roots.
  It observes evidence only; definition, approval, scheduling, lease, dispatch, retry, execution
  and policy authority remain with their owning components.
- Provider verification is **66 passed** with Ruff, `compileall`, CLI-help, diff and bilingual
  UTF-8 checks green. English and German runtime-observation contracts are shipped together.
- The canonical OneDrive module projection and generated module catalogue were refreshed through
  FileCommander. Source/projection SHA-256 hashes match, catalogue JSON is valid and the only
  structural catalogue change is `automation-master`; its catalogue pin is the provider commit
  above.
- TDD first failed because the shipped OCEAN overlay contained no
  `module:automation-runtime` binding. The now-green binding test proves that registry and runtime
  remain distinct logical placements even though both consume `automation-master`.
- Binding overlay hash `516169be3dcbdf5814fbbec285fbfffa33fcef095c8ab4ee2b2b038a2cc43873`
  pins `module:automation-runtime` to its own `automation-runtime` placement and requires
  `automation.runtime.observe`, `automation.runtime.receipt` and
  `automation.runtime.statistics`. The already verified `automation-registry` placement remains
  untouched at its prior pin.

### Controlled apply and installed-provider acceptance

- The read-only plan verifies all **28/28** recipe pins and plans only the new runtime placement;
  it does not overwrite the existing registry checkout.
- A controlled `down` followed by `up --apply` fetched the exact runtime provider commit into
  `C:\_Local_DEV\ocean-full-dev\modules\automation-runtime`, verified clean detached HEAD,
  repository origin, manifest identity and all three required capabilities, then restarted OCEAN.
- The installed state resolves **54 of 65 module references**, leaves **11 optional** module
  references unresolved, resolves **80/80 skills**, has no missing required component and reports
  `full_composition: true`. Runtime status is `running/ok` at
  `http://127.0.0.1:8810/control/`.
- Acceptance executed the installed provider rather than the source checkout. A synthetic native
  provider receipt and closed scheduler SQLite snapshot produced bounded hashed readbacks, one
  immutable `ellmos.automation-runtime-receipt.v1` receipt and bounded success statistics. Raw
  provider detail and scheduler output did not cross the readback boundary.
- The Open OCEAN suite is now **136 passed**. This evidence closes the declared private FULL OCEAN
  development composition only. It is not a fresh foreign-host full-system proof, OPEN OCEAN
  release, BACH-parity proof, visibility change or authorization to modify `PRIVATE.txt`.
- The recipe branch documentation follow-up is pushed at
  `ellmos-development-system@4fa0d4f44451d967c2a5b4cf4bd659828c9dcdd9`; it records the same
  28/28, 54/65 and 80/80 consumer proof without turning branch adoption into a release claim.

### Adaptive continuation pool

Selection remains result-driven rather than ordered. At the next section start, repeat the
`.AI`/Gardener/USMC/policy lift and choose among:

- derive and test a default-deny OPEN OCEAN allowlist independently from FULL OCEAN;
- run the complete fresh-install proof on a non-development host;
- decide whether/how recipe branch tip `4fa0d4f…` is adopted into canonical recipe `main`;
- continue BACH parity work while treating newly discovered BACH-only extraction as exceptional
  and value-gated;
- select shared OCEAN components for SPEEDBOAT only for a concrete proprietary use case;
- keep documentation, root/help surfaces and language variants synchronized in every cycle.

The named checkpoint for this private integration cycle is
`ocean-full-dev-gezeitenstrom-20260829`. It is not a public release tag.
