# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-08

### Added
- **GitHub Actions CI Workflow**: Multi-OS (`ubuntu-latest`, `windows-latest`, `macos-latest`) and multi-version Python matrix (`3.10`, `3.11`, `3.12`, `3.13`) in `.github/workflows/ci.yml` with concurrency control (`cancel-in-progress: true`), ruff linting, bytecode compilation check, and pytest execution.
- **PEP 621 Standard Packaging & Metadata (`pyproject.toml`)**: Standardized project metadata with classifiers (Python 3.10-3.13, OS Independent, Linux, Windows, macOS), pytest configuration (`pythonpath = ["."]`), ruff configuration, and complete ecosystem URLs (`Homepage`, `Repository`, `Issues`, `Changelog`, `Documentation`, `Security`, `Parent Organization`, `Umbrella Ecosystem`).
- **Bilingual Security Policy (`SECURITY.md`)**: Detailed security and privacy invariants covering Local-First & Zero-Egress, Fail-Closed Verification & Transactional Rollback, Mandatory Dry-Run-First Safety Gate, Sandboxed Activation Isolation, and Non-Elevation; includes supported versions table (`0.1.x`), 48-hour response SLA, and official security reporting channels.
- **Automated Metadata & Contract Test Suite (`tests/test_metadata.py`)**: 7 new contract tests validating CI workflow integrity, PEP 621 metadata declarations, bilingual security policy invariants, README badges & documentation parity, llms.txt context synchronization, `.gitignore` hygiene, and offline zero-egress invariants.
- **Machine-Readable Project Context (`llms.txt`)**: Overview of architecture, invariants, repository structure, and verified test suites.
- **Gitignore Hardening**: Enhanced `.gitignore` with synchronization conflict patterns (`*.sync-conflict-*`, `*.conflict`, `*-CONFLIT-*`), test/linter caches (`.ruff_cache/`, `.mypy_cache/`), and temporary backup files.
- **README Status & Shields.io Badges**: Integrated standard ecosystem badges for CI status, test suite passing count, Python versions, platforms, MIT license, Security Policy, Privacy, and ecosystem links in both `README.md` and `README_de.md`.
