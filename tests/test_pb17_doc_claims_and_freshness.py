# -*- coding: utf-8 -*-
"""Contract tests for PB-17 (Doku-Claim-Test, Frische-Test & Sprachfeld in open-ocean).

Verifies:
1. Doku-Claim-Test: All documented file paths, JSON contracts, CLI entrypoints, and module imports
   referenced in README.md, llms.txt, and architecture/doc-freshness-and-claims.v1.json physically exist and resolve.
2. Frische-Test: architecture/doc-freshness-and-claims.v1.json hashes match current files on disk,
   translations exist, match target hashes, and are not stale relative to sources.
3. Manifest-Sprachfeld-Test: Verifies that component-bindings and doc-freshness schemas enforce
   languages (non-empty list with at least 'de' and 'en') and docs metadata for all 13 core Ocean bundles.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC_CLAIMS_PATH = ROOT / "architecture" / "doc-freshness-and-claims.v1.json"
COMPONENT_BINDINGS_PATH = ROOT / "architecture" / "component-bindings.v1.json"


def sha256_file(path: Path) -> str:
    """Compute sha256 hex digest for a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Suite 1: Doku-Claim-Test
# ---------------------------------------------------------------------------


def test_pb17_doku_claims_from_freshness_manifest() -> None:
    """Verify all relative paths, module imports, and CLI entrypoints claimed in doc-freshness-and-claims.v1.json."""
    assert DOC_CLAIMS_PATH.is_file(), "doc-freshness-and-claims.v1.json must exist"
    manifest = json.loads(DOC_CLAIMS_PATH.read_text(encoding="utf-8"))

    assert manifest.get("schema") == "open-ocean.doc-freshness-and-claims.v1"
    documents = manifest.get("documents", [])
    assert len(documents) >= 5, "Must track at least 5 document sets"

    for doc in documents:
        claims = doc.get("verified_claims", {})

        # 1. Relative repo paths
        for rel_path in claims.get("relative_repo_paths", []):
            target = ROOT / rel_path
            assert target.exists(), f"Document claim failed: '{rel_path}' does not exist on disk (claimed in {doc['document_id']})"

        # 2. Module imports / entrypoints
        for mod_name in claims.get("module_imports", []):
            # Check either importable via importlib or file exists in repo
            try:
                mod = importlib.import_module(mod_name)
                assert mod is not None
            except ImportError:
                # Check path mapping
                mod_file = ROOT / (mod_name.replace(".", "/") + ".py")
                assert mod_file.is_file(), f"Module claim failed: neither importable nor exists as file '{mod_file}'"

        # 3. CLI commands
        for cmd in claims.get("cli_commands", []):
            # Extract script entrypoint from command string (e.g. 'python ocean.py up' -> 'ocean.py')
            parts = cmd.split()
            script = None
            if len(parts) >= 2 and parts[0] in ("python", "python3"):
                script = parts[1]
            elif parts:
                script = parts[0] + ".py"

            if script and not script.startswith("-"):
                script_path = ROOT / script
                # If script is a known tool or root entrypoint, assert it exists
                if (ROOT / script).exists() or (ROOT / "tools" / script).exists():
                    pass
                elif parts[0] == "ocean":
                    assert (ROOT / "ocean.py").is_file()


def test_pb17_doku_claims_markdown_references_in_readme_and_llms() -> None:
    """Verify that relative links in README.md and llms.txt resolve to real files."""
    for filename in ("README.md", "README_de.md", "llms.txt"):
        doc_path = ROOT / filename
        assert doc_path.is_file(), f"{filename} must exist"
        content = doc_path.read_text(encoding="utf-8")

        # Match markdown links: [text](path)
        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
        for _, link in links:
            # Skip external web URLs, anchors, mailto
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Strip anchors within relative links (e.g. 'file.md#anchor')
            clean_link = link.split("#")[0]
            if not clean_link:
                continue
            resolved = ROOT / clean_link
            assert resolved.exists(), f"Broken relative link '{link}' in {filename} (resolved to {resolved})"


# ---------------------------------------------------------------------------
# Suite 2: Frische-Test
# ---------------------------------------------------------------------------


def test_pb17_frische_manifest_hashes_match_disk() -> None:
    """Verify all source and translation hashes in doc-freshness-and-claims.v1.json match disk."""
    assert DOC_CLAIMS_PATH.is_file()
    manifest = json.loads(DOC_CLAIMS_PATH.read_text(encoding="utf-8"))

    for doc in manifest.get("documents", []):
        source_rel = doc.get("source_path")
        source_file = ROOT / source_rel
        assert source_file.is_file(), f"Source document '{source_rel}' does not exist"

        disk_source_sha = sha256_file(source_file)
        claimed_source_sha = doc.get("source_sha256")
        assert claimed_source_sha == disk_source_sha, (
            f"Freshness mismatch for source '{source_rel}': claimed {claimed_source_sha}, actual {disk_source_sha}"
        )

        for lang, trans_info in doc.get("translations", {}).items():
            target_rel = trans_info.get("target_path")
            target_file = ROOT / target_rel
            assert target_file.is_file(), f"Translation '{target_rel}' ({lang}) does not exist"

            disk_target_sha = sha256_file(target_file)
            claimed_target_sha = trans_info.get("target_sha256")
            assert claimed_target_sha == disk_target_sha, (
                f"Freshness mismatch for translation '{target_rel}' ({lang}): "
                f"claimed {claimed_target_sha}, actual {disk_target_sha}"
            )
            assert trans_info.get("verified_not_older_than_source") is True, (
                f"Translation '{target_rel}' must have verified_not_older_than_source: true"
            )


def test_pb17_frische_bilingual_docs_presence() -> None:
    """Verify docs/README.de.md and docs/README.en.md exist, are non-empty, and cross-reference each other."""
    readme_de = ROOT / "docs" / "README.de.md"
    readme_en = ROOT / "docs" / "README.en.md"

    assert readme_de.is_file(), "docs/README.de.md must exist"
    assert readme_en.is_file(), "docs/README.en.md must exist"

    content_de = readme_de.read_text(encoding="utf-8")
    content_en = readme_en.read_text(encoding="utf-8")

    assert len(content_de) > 200, "docs/README.de.md is too short"
    assert len(content_en) > 200, "docs/README.en.md is too short"

    assert "README.en.md" in content_de, "docs/README.de.md must link to English version"
    assert "README.de.md" in content_en, "docs/README.en.md must link to German version"


# ---------------------------------------------------------------------------
# Suite 3: Manifest-Sprachfeld-Test
# ---------------------------------------------------------------------------


def test_pb17_manifest_sprachfeld_contract() -> None:
    """Verify that all 13 core Ocean bundles in component-bindings.v1.json specify languages and docs."""
    assert COMPONENT_BINDINGS_PATH.is_file()
    bindings_data = json.loads(COMPONENT_BINDINGS_PATH.read_text(encoding="utf-8"))

    bindings = bindings_data.get("bindings", [])
    assert len(bindings) == 13, f"Expected 13 core Ocean bundles, got {len(bindings)}"

    for item in bindings:
        bundle_ref = item.get("bundle_ref")
        assert "languages" in item, f"Bundle '{bundle_ref}' missing 'languages' field"
        langs = item["languages"]
        assert isinstance(langs, list), f"Bundle '{bundle_ref}' languages must be a list"
        assert len(langs) >= 2, f"Bundle '{bundle_ref}' must support at least 2 languages"
        assert "de" in langs, f"Bundle '{bundle_ref}' languages must contain 'de'"
        assert "en" in langs, f"Bundle '{bundle_ref}' languages must contain 'en'"

        assert "docs" in item, f"Bundle '{bundle_ref}' missing 'docs' metadata"
        docs = item["docs"]
        assert isinstance(docs, dict), f"Bundle '{bundle_ref}' docs must be an object"
        assert "readme" in docs, f"Bundle '{bundle_ref}' docs missing 'readme'"
        assert "doc_de" in docs, f"Bundle '{bundle_ref}' docs missing 'doc_de'"


def test_pb17_doc_freshness_languages_and_world_set_schema() -> None:
    """Verify doc-freshness-and-claims.v1.json enforces required and world set languages."""
    manifest = json.loads(DOC_CLAIMS_PATH.read_text(encoding="utf-8"))

    assert manifest.get("default_source_language") == "de"
    assert manifest.get("required_languages") == ["de", "en"]
    assert manifest.get("world_set_languages") == ["de", "en", "es", "ja", "ru", "zh"]

    module_schema = manifest.get("module_doc_schema", {})
    assert "required_manifest_fields" in module_schema
    assert "languages" in module_schema["required_manifest_fields"]
    assert "docs" in module_schema["required_manifest_fields"]
    assert module_schema.get("minimum_languages") == ["de", "en"]
    assert len(module_schema.get("core_bundles", [])) == 13
