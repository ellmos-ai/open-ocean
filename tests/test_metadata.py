"""Automated contract tests for repository metadata, CI workflows, security policy, and docs parity."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_integrity():
    """Verify GitHub Actions CI workflow configures concurrency, multi-OS matrix, and test steps."""
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow_path.is_file(), "ci.yml workflow must exist"

    content = workflow_path.read_text(encoding="utf-8")
    assert "concurrency:" in content
    assert "cancel-in-progress: true" in content
    assert "actions/checkout@v4" in content
    assert "actions/setup-python@v5" in content
    assert "ubuntu-latest" in content
    assert "windows-latest" in content
    assert "macos-latest" in content
    assert '"3.10"' in content
    assert '"3.11"' in content
    assert '"3.12"' in content
    assert '"3.13"' in content
    assert "ruff check" in content
    assert "compileall" in content
    assert "pytest" in content


def test_pyproject_pep621_metadata():
    """Verify PEP 621 pyproject.toml declares standard metadata, URLs, and pytest pythonpath."""
    pyproject_path = ROOT / "pyproject.toml"
    assert pyproject_path.is_file(), "pyproject.toml must exist"

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    assert project.get("name") == "open-ocean"
    assert project.get("version") == "0.1.0"
    assert project.get("license") == "MIT"

    urls = project.get("urls", {})
    assert urls.get("Homepage") == "https://github.com/ellmos-ai/open-ocean"
    assert urls.get("Repository") == "https://github.com/ellmos-ai/open-ocean.git"
    assert urls.get("Issues") == "https://github.com/ellmos-ai/open-ocean/issues"
    assert urls.get("Changelog") == "https://github.com/ellmos-ai/open-ocean/blob/main/CHANGELOG.md"
    assert urls.get("Documentation") == "https://github.com/ellmos-ai/open-ocean#readme"
    assert urls.get("Security") == "https://github.com/ellmos-ai/open-ocean/blob/main/SECURITY.md"
    assert urls.get("Parent Organization") == "https://github.com/ellmos-ai"
    assert urls.get("Umbrella Ecosystem") == "https://github.com/open-bricks"

    pytest_opts = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    assert "." in pytest_opts.get("pythonpath", [])


def test_security_policy_contract():
    """Verify SECURITY.md policy contains bilingual sections, invariants, SLA, and reporting channels."""
    sec_path = ROOT / "SECURITY.md"
    assert sec_path.is_file(), "SECURITY.md must exist"

    content = sec_path.read_text(encoding="utf-8")
    assert '<a name="english"></a>' in content
    assert '<a name="deutsch"></a>' in content
    assert "Local-First & Zero-Egress Invariant" in content
    assert "Fail-Closed Verification & Transactional Rollback" in content
    assert "Mandatory Dry-Run-First Safety Gate" in content
    assert "Sandboxed Activation Isolation" in content
    assert "Non-Elevation & Least Privilege" in content
    assert "0.1.x" in content
    assert "48 hours" in content or "48 Stunden" in content
    assert "security@ellmos.ai" in content
    assert "support@lukasgeiger.com" in content
    assert "lukas@open-bricks.org" in content
    assert "https://github.com/ellmos-ai/open-ocean/security/advisories" in content


def test_readme_badges_and_parity():
    """Verify README.md and README_de.md contain badges, banner, and navigation links."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README_de.md").read_text(encoding="utf-8")

    assert 'src="assets/banner.png"' in readme_en
    assert 'src="assets/banner.png"' in readme_de
    assert "[Deutsch](README_de.md)" in readme_en
    assert "[English](README.md)" in readme_de

    for doc, name in [(readme_en, "README.md"), (readme_de, "README_de.md")]:
        assert "version-0.1.0" in doc, f"{name} missing version badge"
        assert "python-3.10" in doc, f"{name} missing python badge"
        assert "license-MIT" in doc, f"{name} missing license badge"
        assert "SECURITY.md" in doc, f"{name} missing SECURITY.md reference"
        assert "CHANGELOG.md" in doc, f"{name} missing CHANGELOG.md reference"
        assert "llms.txt" in doc, f"{name} missing llms.txt reference"
        assert "ci.yml" in doc, f"{name} missing CI badge reference"


def test_llms_txt_contract():
    """Verify llms.txt machine-readable documentation and timestamp."""
    llms_path = ROOT / "llms.txt"
    assert llms_path.is_file(), "llms.txt must exist"

    content = llms_path.read_text(encoding="utf-8")
    assert "# open-ocean" in content
    assert "## Project Information" in content
    assert "## Overview" in content
    assert "## Safety & Invariants" in content
    assert "## Repository Structure" in content
    assert "## Usage" in content
    assert "2026-09-09" in content
    assert "https://github.com/ellmos-ai/open-ocean" in content

    installer_target = (ROOT / "architecture" / "INSTALLER-TARGET.md").read_text(
        encoding="utf-8"
    )
    normalized_target = " ".join(
        line.removeprefix("> ").strip() for line in installer_target.splitlines()
    )
    assert "target contract with an implemented supported path" in normalized_target
    assert "This file was written before the installer existed." in normalized_target
    assert "BACH setup parity" in normalized_target


def test_gitignore_hygiene():
    """Verify .gitignore includes sync conflict, lock, and test cache patterns."""
    gitignore_path = ROOT / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore must exist"

    content = gitignore_path.read_text(encoding="utf-8")
    assert "*.sync-conflict-*" in content
    assert "*.conflict" in content
    assert "*-CONFLIT-*" in content
    assert "LOCK*.txt" in content
    assert ".pytest_cache/" in content
    assert ".ruff_cache/" in content
    assert ".coverage" in content


def test_zero_egress_and_offline_invariants():
    """Verify tools directory contains no telemetry or remote tracking calls."""
    tools_dir = ROOT / "tools"
    forbidden_tokens = ["google-analytics", "segment.io", "mixpanel", "sentry.io", "telemetry."]

    for py_file in tools_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"Forbidden tracking/telemetry token '{token}' in {py_file}"
