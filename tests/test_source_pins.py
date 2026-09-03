"""Regression tests for the recipe and Skills Registry source-pin gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools.resolve_bundles import canonical_hash
from tools.source_pins import SourcePinError, repin_source_pins, verify_source_pins


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout.strip()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture(root: Path) -> dict[str, Path | dict]:
    recipe = root / "recipe"
    recipe.mkdir()
    registry = root / "skills" / "registry" / "components.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(b'{"components": []}\n')
    crosswalk = recipe / "manifests" / "skills.registry.crosswalk.v1.json"
    crosswalk.parent.mkdir(parents=True)
    crosswalk.write_bytes(b'{"skills": []}\n')

    registry_uri = (
        "repo://ellmos-ai/skills@"
        "08e1fe212d58075bc00e2f8403c104a507857c05/registry/components.json"
    )
    bindings = {
        "schema": "ellmos.component-registry-bindings.v1",
        "sources": {
            "registry:skills-components": {
                "kind": "skill-registry",
                "uri": registry_uri,
                "record_collection": "components",
                "record_id_field": "id",
                "sha256": _sha256(registry.read_bytes()),
            },
            "crosswalk:skills": {
                "kind": "skill-crosswalk",
                "uri": "repo://manifests/skills.registry.crosswalk.v1.json",
                "record_collection": "skills",
                "record_id_field": "registry_component_id",
                "sha256": _sha256(crosswalk.read_bytes()),
            },
        },
    }
    bindings["content_hash"] = canonical_hash(bindings)
    bindings_path = recipe / "manifests" / "component.registry.bindings.v1.json"
    _write_json(bindings_path, bindings)

    _git(recipe, "init", "--initial-branch=main")
    _git(recipe, "config", "user.name", "OCEAN Test")
    _git(recipe, "config", "user.email", "ocean-test@example.invalid")
    _git(recipe, "remote", "add", "origin", "https://example.invalid/recipe.git")
    _git(recipe, "add", ".")
    _git(recipe, "commit", "-m", "fixture recipe")
    commit = _git(recipe, "rev-parse", "HEAD")

    contract = {
        "schema": "ellmos.open-ocean-source-pins.v1",
        "id": "fixture-source-pins",
        "version": "1.0.0",
        "authority": {"kind": "integration-pin", "runtime_authority": False},
        "recipe": {
            "repository": "https://example.invalid/recipe.git",
            "commit": commit,
            "component_bindings": {
                "path": "manifests/component.registry.bindings.v1.json",
                "content_hash": bindings["content_hash"],
            },
            "skills_crosswalk": {
                "path": "manifests/skills.registry.crosswalk.v1.json",
                "sha256": _sha256(crosswalk.read_bytes()),
            },
        },
        "skills_registry": {
            "uri": registry_uri,
            "sha256": _sha256(registry.read_bytes()),
        },
    }
    contract["content_hash"] = canonical_hash(contract)
    contract_path = root / "source-pins.json"
    _write_json(contract_path, contract)
    return {
        "recipe": recipe,
        "registry": registry,
        "contract": contract,
        "contract_path": contract_path,
    }


def _rewrite_contract(fixture: dict[str, Path | dict]) -> None:
    contract = fixture["contract"]
    assert isinstance(contract, dict)
    contract["content_hash"] = canonical_hash(contract)
    path = fixture["contract_path"]
    assert isinstance(path, Path)
    _write_json(path, contract)


def test_exact_source_pins_return_a_portable_verification_receipt(tmp_path: Path):
    fixture = _fixture(tmp_path)

    verification = verify_source_pins(
        fixture["contract_path"],
        fixture["recipe"],
        fixture["registry"],
    )
    receipt = verification.receipt

    contract = fixture["contract"]
    assert isinstance(contract, dict)
    assert receipt == {
        "status": "verified",
        "contract": str(fixture["contract_path"].resolve()),
        "content_hash": contract["content_hash"],
        "recipe": {
            "repository": "https://example.invalid/recipe.git",
            "commit": contract["recipe"]["commit"],
            "component_bindings_content_hash": contract["recipe"]["component_bindings"]["content_hash"],
            "skills_crosswalk_sha256": contract["recipe"]["skills_crosswalk"]["sha256"],
        },
        "skills_registry": {
            "uri": contract["skills_registry"]["uri"],
            "sha256": contract["skills_registry"]["sha256"],
        },
    }
    assert verification.skills_registry == {"components": []}


def test_changed_skills_registry_fails_closed(tmp_path: Path):
    fixture = _fixture(tmp_path)
    registry = fixture["registry"]
    assert isinstance(registry, Path)
    registry.write_bytes(b'{"components": [{"id": "changed"}]}\n')

    with pytest.raises(SourcePinError, match="Skills Registry SHA-256 mismatch"):
        verify_source_pins(fixture["contract_path"], fixture["recipe"], registry)


def test_dirty_or_wrong_recipe_checkout_fails_closed(tmp_path: Path):
    fixture = _fixture(tmp_path)
    recipe = fixture["recipe"]
    assert isinstance(recipe, Path)
    (recipe / "uncommitted.txt").write_text("foreign\n", encoding="utf-8")

    with pytest.raises(SourcePinError, match="not clean"):
        verify_source_pins(fixture["contract_path"], recipe, fixture["registry"])

    (recipe / "uncommitted.txt").unlink()
    _git(recipe, "commit", "--allow-empty", "-m", "new head")
    with pytest.raises(SourcePinError, match="recipe commit mismatch"):
        verify_source_pins(fixture["contract_path"], recipe, fixture["registry"])


def test_provider_binding_pin_is_checked_independently(tmp_path: Path):
    fixture = _fixture(tmp_path)
    contract = fixture["contract"]
    assert isinstance(contract, dict)
    contract["recipe"]["component_bindings"]["content_hash"] = "0" * 64
    _rewrite_contract(fixture)

    with pytest.raises(SourcePinError, match="provider binding content_hash mismatch"):
        verify_source_pins(
            fixture["contract_path"],
            fixture["recipe"],
            fixture["registry"],
        )


def test_missing_recipe_path_is_a_controlled_source_pin_failure(tmp_path: Path):
    fixture = _fixture(tmp_path)
    contract = fixture["contract"]
    assert isinstance(contract, dict)
    contract["recipe"]["component_bindings"]["path"] = "manifests/missing.json"
    _rewrite_contract(fixture)

    with pytest.raises(SourcePinError, match="component_bindings path is unavailable"):
        verify_source_pins(
            fixture["contract_path"],
            fixture["recipe"],
            fixture["registry"],
        )

def _advance_fixture(fixture: dict[str, Path | dict]) -> str:
    """Move the recipe one commit forward with a new registry, like a real re-pin trigger."""
    recipe = fixture["recipe"]
    registry = fixture["registry"]
    assert isinstance(recipe, Path) and isinstance(registry, Path)
    registry.write_bytes(b'{"components": [{"id": "skill:new"}]}\n')
    bindings_path = recipe / "manifests" / "component.registry.bindings.v1.json"
    bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
    source = bindings["sources"]["registry:skills-components"]
    source["uri"] = "repo://ellmos-ai/skills@" + "1" * 40 + "/registry/components.json"
    source["sha256"] = _sha256(registry.read_bytes())
    bindings.pop("content_hash", None)
    bindings["content_hash"] = canonical_hash(bindings)
    _write_json(bindings_path, bindings)
    _git(recipe, "add", ".")
    _git(recipe, "commit", "-m", "fixture recipe: registry moved")
    return _git(recipe, "rev-parse", "HEAD")


def test_repin_is_check_only_by_default_and_reports_the_move(tmp_path: Path):
    fixture = _fixture(tmp_path)
    new_commit = _advance_fixture(fixture)
    contract_path = fixture["contract_path"]
    assert isinstance(contract_path, Path)
    before = contract_path.read_bytes()

    report = repin_source_pins(contract_path, fixture["recipe"], fixture["registry"])

    assert report["status"] == "would-update"
    assert report["written"] is False
    assert report["current"]["recipe_commit"] == new_commit
    assert report["current"]["skills_registry"]["uri"].endswith("@" + "1" * 40 + "/registry/components.json")
    assert contract_path.read_bytes() == before
    with pytest.raises(SourcePinError, match="recipe commit mismatch"):
        verify_source_pins(contract_path, fixture["recipe"], fixture["registry"])


def test_repin_write_rewrites_the_contract_and_the_gate_accepts_it(tmp_path: Path):
    fixture = _fixture(tmp_path)
    new_commit = _advance_fixture(fixture)
    contract_path = fixture["contract_path"]
    assert isinstance(contract_path, Path)

    report = repin_source_pins(contract_path, fixture["recipe"], fixture["registry"], write=True)

    assert report["status"] == "updated" and report["written"] is True
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["recipe"]["commit"] == new_commit
    assert contract["content_hash"] == canonical_hash(contract)
    assert contract["skills_registry"]["sha256"] == _sha256(fixture["registry"].read_bytes())
    verification = verify_source_pins(contract_path, fixture["recipe"], fixture["registry"])
    assert verification.receipt["status"] == "verified"
    again = repin_source_pins(contract_path, fixture["recipe"], fixture["registry"])
    assert again["status"] == "unchanged"


def test_repin_refuses_a_dirty_recipe_and_registry_bytes_that_disagree_with_the_binding(tmp_path: Path):
    fixture = _fixture(tmp_path)
    recipe = fixture["recipe"]
    registry = fixture["registry"]
    assert isinstance(recipe, Path) and isinstance(registry, Path)
    (recipe / "manifests" / "scratch.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SourcePinError, match="not clean"):
        repin_source_pins(fixture["contract_path"], recipe, registry)
    (recipe / "manifests" / "scratch.json").unlink()

    registry.write_bytes(b'{"components": ["drift"]}\n')
    with pytest.raises(SourcePinError, match="differ from the provider binding pin"):
        repin_source_pins(fixture["contract_path"], recipe, registry)
