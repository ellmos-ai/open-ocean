# Installer target structure

> **Status: documentation, not code.** Nothing in this file exists yet. It records what the
> installer has to become so that the gap is written down instead of implied — and so that a
> reader can tell the difference between a plan and a product.

## Why there is no installer yet

The decision on *what* to build was made: a hybrid — a pilot chassis plus three mechanisms
carried over from the original full instance (rollback on update, a distribution-type switch, and
a resolver for exporting skills). The decision on *when* deferred the build. The publication
phase is what makes it due again, because without an installer "installable" stays a claim.

Until it exists, a recipe is executed by an agent CLI the user already runs. That is the honest
description of v0.x, and it belongs on the front page rather than in a footnote.

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

1. **Where components land** depends on the host agent CLI, and there is more than one. Whether
   the installer targets one, several, or an abstraction over them is undecided.
2. **How a wave lands in an existing installation** — a recipe repository that releases wave by
   wave means installations will sit at different waves. Upgrade is therefore a first-class case,
   not an afterthought.
3. **What "installed" means for a skill** versus for a module: one is a file in a registry path,
   the other a repository with its own dependencies.
