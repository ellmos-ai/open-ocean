# Open OCEAN TODO

*[Deutsch](TODO_de.md)*

## Immediate reliability follow-ups

- [x] Added a workspace-scoped interprocess start lock (`_start_lock`, `ocean.start.lock`,
  OS-held byte-range/flock lock, released by the OS if the starter dies; second concurrent
  start fails closed at the CLI). Original description: Two direct lifecycle invocations can
  currently pass the empty-state preflight before either supervisor writes runtime state. The
  ASUS-GEI logon task avoids this by disabling `StartWhenAvailable` and using one trigger, but the
  lifecycle itself must fail closed under simultaneous starts.
- [x] Favicon served: `ellmos-core` answers `/favicon.ico` with its PWA icon (ellmos-core
  `6185504`); takes effect on hosts once their runtime provider copy carries that commit.
  Original description: Serve an OCEAN favicon or remove the favicon request; current browser
  acceptance is healthy but records one non-functional `/favicon.ico` 404.
- [ ] Perform a real ASUS-GEI reboot and read back the unchanged `EllmosOceanFullUserStart` task,
  exact tagged checkout, process tuple, port ownership, HTTP identity and Full Ocean readiness.
  **2026-09-02: happened de facto and FAILED.** After the 21:04 boot the logon task ran at
  21:07:23 and exited 4 (runtime child exit 1 after 21 s, port 8810 never bound). Cause: 12 of
  14 runtime providers on the spec PYTHONPATH are OneDrive read copies, and OneDrive.exe only
  started at 21:14:27 — seven minutes after the task. A manual `ocean.py start` afterwards is
  green. Ticket T-20260902-313385481 (place providers into the workspace; no OneDrive runtime path;
  child stderr into `logs/runtime.log`). Interim on ASUS-GEI: task restart-on-failure 5× every
  2 min (XML backup in `logs/`). Stays open until a reboot readback is green.
  **2026-09-02, later same day: both code fixes landed (b59d1ee).**
  `fetch_place.plan_and_fetch()` now copies ("places") every Resolve-found module with no exact
  binding into `<workspace>/modules/<catalog_id>` on `--apply` and repoints its `local_path`
  there, exactly like the pre-existing exact-bound-provider placement; `ocean.py start` tees
  `sys.stderr` into `<workspace>/logs/runtime.log` (pythonw has no console, so a headless
  `LifecycleError` print — or any unhandled traceback, since Python's default excepthook also
  writes to stderr — used to vanish with nothing but the bare exit code). Re-verified on
  ASUS-GEI without a reboot: the pinned runtime checkout was fast-forwarded to `b59d1ee`,
  `ocean.py down` + `up --apply` (same bundles-root/system-manifest/catalog/skills-registry as
  the original install) re-ran cleanly, and the resulting `ocean.runtime-spec.json` now carries
  **zero** OneDrive entries across all 14 PYTHONPATH paths (all under
  `C:\_Local_DEV\ocean-full\modules\`). `Start-ScheduledTask EllmosOceanFullUserStart` after an
  `ocean.py down` reproduced the real logon action end-to-end: `LastTaskResult 0`, process
  ancestry `pythonw ocean.py start` → `pythonw runtime_supervisor.py` → `pythonw
  ocean_runtime.py` (PID 26608) listening on 8810, `/api/health` → `{"ok":true,...}`, and the
  stderr-tee header line plus the child's own uvicorn output both landed in
  `logs/runtime.log` as designed. **This is not the reboot readback the checkbox above asks
  for** — OneDrive was already running throughout this test, so it cannot reproduce the actual
  race (OneDrive not yet mounted at logon); it only proves the fix removes that race by
  construction (no OneDrive path left to race against) and that the task/process/port/health
  chain works end-to-end on the fixed checkout. Stays open until an actual ASUS-GEI reboot
  confirms it live.
  **2026-09-10, a real boot finally happened — and it FAILED AGAIN, for a different reason.**
  `LastBootUpTime 2026-09-10T19:42:24+02:00`; the logon task ran at 19:42:38 and exited 4 once
  more. The OneDrive cause was gone (`ocean.runtime-spec.json`: zero OneDrive entries, all 14
  PYTHONPATH directories local) and the pinned checkout already carried the 60 s health budget
  (`bb12d541`). The child lived 57.5 s (`started_at 17:43:27.8Z` → `stopped_at 17:44:25.4Z`)
  without emitting a single uvicorn line — on every successful start `Started server process`
  appears within seconds, so it never got past its imports.
  **2026-09-12 root cause, measured: the start is file-cache dominated, and 60 s sits right
  between the warm and the cold figure.** Two runs of the same unchanged install, same task,
  same checkout: the first start after two days of inactivity reached `/api/health` 200 after
  **209.8 s**; a second start immediately afterwards reached it after **38.9 s** — a factor of
  5.4 from cache state alone. That single number explains the whole history: every demand start
  and every staging probe was warm and green (49.6 s on 2026-09-09), every boot-time start was
  cold and died at the budget. Note the 209.8 s run was itself a *demand* start — it would have
  failed under the old 60 s budget too, which is the first direct proof that the budget, not a
  defect, is what kills the cold start. Imports do not explain it (measured with the real spec
  env: `import ellmos_core.app` + `OceanOriginApp()` + both validators = 10.8 s warm, 23.3 s on
  a cold file cache; `init_db()` runs against a 139 KB SQLite file).
  **Fix (host-local, no code change): the logon task now passes `--health-timeout 600`**, which
  is what that option was added for (`43072b1`/`b59d1ee`: "a generous ceiling only matters for
  the genuinely-just-slow case"). A truly dead process still fails fast via the `status ==
  "stopped"` break, so the ceiling costs nothing on success or on crash; it only buys time in
  the "alive but slow" case. The 60 s default stays as-is for interactive use. Task XML backup:
  `logs/EllmosOceanFullUserStart.before-health-timeout-20260912.xml`.
  **Verified end-to-end with the final value** (2026-09-12 09:00:28, from a stopped runtime):
  `LastTaskResult 0`, sole listener `127.0.0.1:8810` (PID 5184), `/api/health` 200 after 38.9 s,
  receipt `running`. **Still open until a real reboot confirms it** — the cold path itself cannot
  be reproduced without one. WORKSTATION-LG most likely needs the same task argument (check
  there, do not assume).
- [ ] Find out why an OCEAN start needs 39 s warm and 210 s cold at all. Ruled out by
  measurement on 2026-09-12 (see the reboot item above): module imports, `OceanOriginApp()`,
  `validate_production_security()`, `validate_model_locality()` and `init_db()` together account
  for ~11 s warm. The remainder sits between the child spawn and its first health answer, i.e.
  inside `uvicorn.run()` / the ASGI lifespan of the `ellmos-core` provider — a different module,
  so this belongs to its own investigation. Until it is understood, the logon task's health
  budget is a compensation, not a cure.
- [x] Fixed the `--host` argument on `ocean.py up` (7d4de09): `up` now carries the
  same `choices=["127.0.0.1", "localhost"]` as `start`, so a wrong value fails at the parser
  instead of deep inside the lifecycle. Follow-up done: the same-named
  `--host` in `tools/ocean_dev.py` (a skill-host adapter there, not a network bind) is now
  `--skill-host`; `--host` stays accepted as a legacy alias, no caller breaks. Original description:
  Fix the `--host` argument on `ocean.py up`: `ocean.py` and `tools/ocean_dev.py` each define
  an independent `--host` parameter with the same name; `ocean.py` never forwards its `--host` to
  the `ocean_dev.py` subprocess, which always falls back to its own default `"claude-code"`. A
  prescribed `--host claude-code` on `up` therefore aborts deterministically with
  `LifecycleError`; omit `--host` on `up` (default `127.0.0.1`), as every successful run in the
  build plan does.
- [x] Added the readiness gate for `up --apply` (7d4de09): the new
  `_assert_composition_complete` in `ocean_lifecycle.py` withholds the runtime and names the
  missing required components. Composition and install state are written BEFORE the gate on
  purpose, so artefacts and the report stay available for diagnosis. (This item existed only
  in TODO_de.md until 2026-08-30 — the two language versions had drifted apart.)
- [x] Re-measured on 2026-08-30; no reference correction is required. At recipe-provider pin
  `1b461c9cb900ada15b8e104f2586a6b4a1ea5278`,
  `manifests/skills.registry.crosswalk.v1.json` is an 81-record identity map whose declared
  collection is the top-level `skills` object. The same binding contract separately declares the
  native Skills Registry's `components.json` and its top-level `components` array. OCEAN correctly
  uses the latter to resolve/install skills and now fails closed with an explicit schema reason if
  the crosswalk is supplied as that registry.
- [x] Closed the reproducibility implementation for `T-20260830-702817310` in a bounded review
  slice. Recipe-provider PR `ellmos-development-system#91` refreshes only the independently
  re-measured Skills Registry and Crosswalk pins and records the Registry's immutable repository
  URI. OCEAN now ships a content-hashed source-pin contract and rejects a dirty/wrong recipe
  checkout, provider-binding drift, Crosswalk drift or Skills Registry drift before Resolve/Fetch.
  The review branches are not merged or released by this item; unrelated module/MCP source drift
  remains outside its scope.

## Release breadth

- [ ] Run a complete fresh Full Ocean installation on a non-development host.
- [ ] Derive and test the default-deny OPEN OCEAN public allowlist independently from FULL OCEAN.
- [ ] Continue BACH functional-parity work; treat newly discovered BACH-only extraction as an
  exceptional, value-gated module cycle.
- [x] (2026-09-02) Merged: `gardener` #4 (master ddd3a84), `ellmos-controlcenter-mcp` #9 (main 34cd95d); `policy-registry` #3 closed in favour of the decision-index path slice (https://github.com/ellmos-ai/policy-registry/pull/4). Adoption (host-local registry seed, ControlCenter config, ccm 0.6.0 npm release) is still open. Original: Merge and adopt the pending governance PRs (`policy-registry` #3, `gardener` #4,
  `ellmos-controlcenter-mcp` #9) — all open, mergeable, CI green as of 2026-08-30, none merged
  yet; host-local registry init, Gardener system sources and ControlCenter configuration only
  become relevant afterward.
- [ ] Explore device-bound OS-account coupling for OCEAN user identity (a Windows/macOS account
  per device) instead of a separate app password; motivated by the WORKSTATION-LG install running
  without an OCEAN user while `/control/` and `/api/health` remain reachable without auth.

These items do not authorize publication, a visibility change or removal of `PRIVATE.txt`.
