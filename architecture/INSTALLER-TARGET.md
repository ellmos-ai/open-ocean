# Installer target structure

> **Status: target contract with an implemented supported path.** This file was written before
> the installer existed. Since 2026-08-18, the six stages below are implemented for the supported
> component path in `tools/resolve_bundles.py`, `tools/fetch_place.py`, `tools/host_adapters.py`
> and `tools/ocean_dev.py`. Current evidence and remaining limits live in
> `OCEAN-DEV-BUILD-PLAN_2026-08-18.md`; this file retains the original target and invariants.

## Why this target document was created

The decision on *what* to build was a hybrid — a pilot chassis plus three mechanisms carried over
from the original full instance (rollback on update, a distribution-type switch, and a resolver
for exporting skills). The initial decision on *when* deferred the build. User decision option
`b` on 2026-08-18 lifted that deferral and authorized the staged implementation recorded in the
build plan.

The implemented v0.x path is still deliberately narrow: a recipe is consumed through the OCEAN
CLI and its host-adapter boundary. This is not a claim of universal host support, BACH setup
parity, or an OPEN OCEAN release.

## What the installer has to do

| Step | Task | Why it is not trivial |
|---|---|---|
| **Resolve** | Expand a bundle to a flat list of components, applying recorded choices and merging duplicates | Members overlap by design, so the merge is not optional. Synthetic bundles expand to their members first |
| **Verify** | Check each recipe against its `content_hash` before acting on it | A recipe that installs software must be verifiable, or the audit argument collapses |
| **Fetch** | Obtain each component from its declared source | Sources differ in kind: repositories, a skill registry, and access surfaces that are not ours to fetch at all |
| **Place** | Put components where the runtime expects them | The layout is the runtime's, not the recipe's; the recipe says *what*, the runtime says *where* |
| **Activate** | Wire the components into the host agent CLI | The one step that has no equivalent in a package manager: the target is an agent, not a filesystem |
| **Roll back** | Restore the previous state when a step fails | Carried over from the original instance, which already solved this |

## What it must not do

- **Not decide visibility.** Publishing and installing are different acts.
- **Not resolve a recipe it cannot verify.** A failed hash check stops the run; it does not warn
  and continue.
- **Not fetch access surfaces.** Commercial providers are reached through their own CLI or app.
  The recipe declares the dependency; the installer does not acquire an account.
- **Not write into the recipe repository.** The projection runs one way.

## Open questions, named rather than assumed

1. **Partially resolved — where components land.** The supported path uses the vendor-neutral
   `HostAdapter` boundary with a `claude-code` adapter. Additional host adapters remain open.
2. **Open — how a wave lands in an existing installation.** A recipe repository that releases
   wave by wave means installations will sit at different waves. Upgrade remains a first-class
   case, not an afterthought.
3. **Resolved for the supported component path — what "installed" means.** Skills are copied
   from their verified registry source into the sandboxed host target; modules are placed as
   exact, clean repository pins. Access surfaces remain declarations and are never fetched.
   Broader component kinds remain open.
