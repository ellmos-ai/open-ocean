# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-09-09

### Added
- **Bilingual README Architecture & Discoverability**: Full structural and anchor parity across `README.md` and `README_de.md`, integrated 14-point Quick Navigation, modern Shields.io badges, and enriched documentation.
- **Dual-Mermaid Diagrams**: Interactive system architecture flowchart (`flowchart TD`) and end-to-end package resolution, verification, staging, and transactional rollback lifecycle diagram (`sequenceDiagram` with autonumbering) in both language editions.
- **Governance & Runtime Invariants Matrix**: 10 core architectural invariants (`INV-LOCAL-01` through `INV-SLA-10`) detailing offline guarantees, fail-closed verification, transactional rollbacks, sandboxed activations, non-elevation, and SLA bounds.
- **Sibling Ecosystem & Partner Repositories**: Cross-referencing 16+ partner repositories across `ellmos-ai`, `dev-bricks`, `file-bricks`, `doc-bricks`, `entertain-and-more`, and `open-bricks`.
- **Security Policy Hardening (`SECURITY.md`)**: Added `security@open-bricks.org` and a binding 5-business-day triage guarantee in both German and English sections.
- **Third-Party Licenses Inventory (`THIRD_PARTY_LICENSES.md`)**: Documented zero-external-runtime-dependencies invariant and permissive licensing of development tooling.
- **Local Marketing Log (`MARKETING-LOG.txt`)**: Documented discoverability status, SEO keywords, and post-sluice directory listings strategy.
- **Automated Contract Tests (`tests/test_metadata.py`)**: Expanded test suite verifying 14-point navigation anchors, Mermaid syntax, invariants completeness, and licenses.
- **LLM Context Synchronization (`llms.txt`)**: Bumped version to 0.1.1 and refreshed timestamp to 2026-09-09.

## [0.1.0] - 2026-09-08

### Added
- **GitHub Actions CI Workflow**: Multi-OS (`ubuntu-latest`, `windows-latest`, `macos-latest`) and multi-version Python matrix (`3.10`, `3.11`, `3.12`, `3.13`) in `.github/workflows/ci.yml` with concurrency control (`cancel-in-progress: true`), ruff linting, bytecode compilation check, and pytest execution.
- **PEP 621 Standard Packaging & Metadata (`pyproject.toml`)**: Standardized project metadata with classifiers (Python 3.10-3.13, OS Independent, Linux, Windows, macOS), pytest configuration (`pythonpath = ["."]`), ruff configuration, and complete ecosystem URLs (`Homepage`, `Repository`, `Issues`, `Changelog`, `Documentation`, `Security`, `Parent Organization`, `Umbrella Ecosystem`).
- **Bilingual Security Policy (`SECURITY.md`)**: Detailed security and privacy invariants covering Local-First & Zero-Egress, Fail-Closed Verification & Transactional Rollback, Mandatory Dry-Run-First Safety Gate, Sandboxed Activation Isolation, and Non-Elevation; includes supported versions table (`0.1.x`), 48-hour response SLA, and official security reporting channels.
- **Automated Metadata & Contract Test Suite (`tests/test_metadata.py`)**: 7 new contract tests validating CI workflow integrity, PEP 621 metadata declarations, bilingual security policy invariants, README badges & documentation parity, llms.txt context synchronization, `.gitignore` hygiene, and offline zero-egress invariants.
- **Machine-Readable Project Context (`llms.txt`)**: Overview of architecture, invariants, repository structure, and verified test suites.
- **Gitignore Hardening**: Enhanced `.gitignore` with synchronization conflict patterns (`*.sync-conflict-*`, `*.conflict`, `*-CONFLIT-*`), test/linter caches (`.ruff_cache/`, `.mypy_cache/`), and temporary backup files.
- **README Status & Shields.io Badges**: Integrated standard ecosystem badges for CI status, test suite passing count, Python versions, platforms, MIT license, Security Policy, Privacy, and ecosystem links in both `README.md` and `README_de.md`.
