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
- [ ] Add a readiness gate to `up --apply`: it does not verify provider completeness before
  starting the runtime — a failed provider fetch still starts an incomplete composition
  (`ocean_lifecycle.py:546-596`; readiness is only reported, never enforced).
- [x] Added the readiness gate for `up --apply` (7d4de09): the new
  `_assert_composition_complete` in `ocean_lifecycle.py` withholds the runtime and names the
  missing required components. Composition and install state are written BEFORE the gate on
  purpose, so artefacts and the report stay available for diagnosis. (This item existed only
  in TODO_de.md until 2026-08-30 — the two language versions had drifted apart.)
- [ ] (No longer reproducible as of 2026-08-30 — re-measure before acting: `resolve_bundles.py`
  already points `DEFAULT_SKILLS_REGISTRY` at `components.json` and explains the missing
  crosswalk file in its own text. Kept until someone has checked the contract reference
  itself.)
  Correct the `manifests/skills.registry.crosswalk.v1.json` reference in the
  component-registry-bindings contract: it is not present with a usable `components` array in the
  bundles checkout; the actually usable source is `components.json` from the Skills Registry.
  Already flagged as a known gap in the tool's own comment.

## Release breadth

- [ ] Run a complete fresh Full Ocean installation on a non-development host.
- [ ] Derive and test the default-deny OPEN OCEAN public allowlist independently from FULL OCEAN.
- [ ] Continue BACH functional-parity work; treat newly discovered BACH-only extraction as an
  exceptional, value-gated module cycle.
- [ ] Merge and adopt the pending governance PRs (`policy-registry` #3, `gardener` #4,
  `ellmos-controlcenter-mcp` #9) — all open, mergeable, CI green as of 2026-08-30, none merged
  yet; host-local registry init, Gardener system sources and ControlCenter configuration only
  become relevant afterward.
- [ ] Explore device-bound OS-account coupling for OCEAN user identity (a Windows/macOS account
  per device) instead of a separate app password; motivated by the WORKSTATION-LG install running
  without an OCEAN user while `/control/` and `/api/health` remain reachable without auth.

These items do not authorize publication, a visibility change or removal of `PRIVATE.txt`.
