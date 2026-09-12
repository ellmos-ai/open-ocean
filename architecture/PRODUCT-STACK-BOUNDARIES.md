# Product stack boundaries

*[Deutsch](PRODUKT-STACK-GRENZEN.md)*

> **Status:** Ratified user decision, 2026-08-29. This document defines product
> membership; it does not authorize runtime activation, publication, repository
> visibility changes, or a release.

## Product algebra

```text
OPEN OCEAN = PUBLIC
PRIVATE OCEAN = PRIVATE_NON_PROPRIETARY
FULL OCEAN = OPEN OCEAN + PRIVATE OCEAN

SPEEDBOAT = PROPRIETARY
            + SELECTED_PUBLIC
            + SELECTED_PRIVATE_NON_PROPRIETARY
```

| Product | Includes | Excludes | Relationship |
|---|---|---|---|
| **OPEN OCEAN** | Public OCEAN components | Private and proprietary components | Public OCEAN base and the product this repository will publish |
| **PRIVATE OCEAN** | Private, non-proprietary OCEAN components | Proprietary components | Private layer of the OCEAN family |
| **FULL OCEAN** | OPEN OCEAN + PRIVATE OCEAN | Proprietary components | Complete local development and test composition for OCEAN |
| **SPEEDBOAT** | Proprietary components plus explicitly selected OPEN-/PRIVATE-OCEAN parts | Every unselected OCEAN component | Independent sibling stack; not an OCEAN edition or overlay |

## The Speedboat metaphor is an architecture rule

Speedboat navigates the ocean. It may use selected waters or travel between
islands, but it is not the ocean and does not inherit the whole ocean.

In machine terms:

- SPEEDBOAT has its own manifest, runtime, origin, state, release, and roadmap
  boundaries.
- `inherits_from` is empty.
- Shared OCEAN bundles and modules enter SPEEDBOAT only through explicit
  allowlists.
- A shared catalog is discovery infrastructure, not product inheritance.

## Compatibility and migration

The V4 recipe schema keeps the technical class token `hosted-private` to avoid a
wide hash and resolver migration. At the product boundary it maps to
`proprietary` and is `SPEEDBOAT-only`. The two current bundles in that class are
`ellmos-multitenancy-bundle` and `ellmos-saas-operations-bundle`.

The technical manifest ID `ellmos-development-fullsystem` remains the current
FULL OCEAN identifier. Product names do not require an immediate physical repo or
ID rename.

Repository visibility is a separate axis. A private repository may contain
PRIVATE OCEAN substance or proprietary SPEEDBOAT substance; only the product
contract and explicit manifests/allowlists decide membership.

## Current composition consequence

FULL OCEAN now consumes the 28 OCEAN-eligible platform/domain bundles. The two
proprietary bundles no longer count as FULL OCEAN requirements and must not create
OCEAN completeness gaps. SPEEDBOAT declares those two bundles independently and
currently selects no shared OCEAN bundle or module.

The machine-readable source is
`ellmos-development-system/contracts/product-stack-boundary-contract.v1.json`.
Until that recipe branch is canonically adopted, this repository consumes the
pushed integration source explicitly and does not claim a `main`-branch cutover.

## Acceptance rules

- OPEN OCEAN contains only public OCEAN components.
- PRIVATE OCEAN contains only private non-proprietary OCEAN components.
- FULL OCEAN is exactly OPEN OCEAN + PRIVATE OCEAN.
- Proprietary components do not block FULL OCEAN completion.
- SPEEDBOAT inherits no OCEAN product.
- Every shared SPEEDBOAT component has an explicit selection record.
