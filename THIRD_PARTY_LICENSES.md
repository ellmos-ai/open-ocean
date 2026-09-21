# Third-Party Licenses & Dependency Inventory

`open-ocean` is designed from first principles to be local-first, zero-egress, and minimal.

## Runtime Dependencies

The core installer and lifecycle mechanisms rely on the Python Standard Library. The read-only
`ocean inspect` adapter additionally uses the same Ed25519 implementation as its pinned native
System Explorer provider:

| Package | Purpose | License | Source / Upstream |
|---|---|---|---|
| **cryptography** | Verify signed Actual-Self evidence through System Explorer | Apache-2.0 OR BSD-3-Clause | [pyca/cryptography](https://github.com/pyca/cryptography) |

Standard-library components include:
- `argparse` — Command-line argument parsing
- `dataclasses` — Structured state and receipt modeling
- `hashlib` — SHA-256 cryptographic verification of bundle manifests and components
- `json` — Manifest expansion and activation log serialization
- `pathlib` — Cross-platform path abstraction and file manipulation
- `shutil` — Atomic copy and directory management
- `subprocess` — Local git and host process execution
- `tomllib` (Python 3.11+) / `tomli` (Python 3.10) — PEP 621 metadata parsing
- `urllib.request` — Deterministic asset retrieval (fail-closed, SHA-verified)

No external telemetry, cloud SDKs, tracking frameworks, or analytics packages are bundled, loaded, or executed.

---

## Development & Test Dependencies

The following tools are used during development, testing, and continuous integration:

| Package | Purpose | License | Source / Upstream |
|---|---|---|---|
| **pytest** | Test runner & contract assertion framework | MIT | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) |
| **ruff** | Fast Python linter & code formatter | MIT / Apache-2.0 | [astral-sh/ruff](https://github.com/astral-sh/ruff) |
| **setuptools** | Packaging & distribution build backend | MIT | [pypa/setuptools](https://github.com/pypa/setuptools) |
| **tomli** | TOML parser fallback for Python 3.10 | MIT | [hukkin/tomli](https://github.com/hukkin/tomli) |

---

## Summary & Compliance

All direct components used across `open-ocean` use permissive MIT, Apache-2.0, or BSD licensing.
