#!/usr/bin/env python3
"""Project bundle recipes from the private composition source into this repository.

The source repository stays authoritative and complete. What arrives here is a
lossy projection of it: the strip rules declared in the source contract
``contracts/github-export-projection.v1.json`` decide what is removed or
rewritten on the way out. The rules live in that contract as data, not in this
file, so the redaction can be audited without reading code.

Run it twice against the same source commit and the second run produces no
diff. That is the point: a projection that cannot be reproduced cannot be
checked.

    python tools/export_from_source.py --source <path-to-source-worktree>
    python tools/export_from_source.py --source <path> --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = "contracts/github-export-projection.v1.json"
# --source is required on purpose: hardcoding a checkout path would bake one
# machine's layout into a repository meant to be readable from anywhere.
SOURCE_ENV = "OPEN_OCEAN_SOURCE"


def path_prefix_pattern(prefixes: list[str]) -> re.Pattern[str] | None:
    """Build the S7 matcher from the prefixes the contract names.

    Deliberately not hardcoded: the prefixes describe the source's internal
    layout, so they belong in the private contract rather than in a file that
    ships publicly. A prefix is stripped together with any dot-prefixed
    directories under it, leaving the document reference itself. The lookahead
    keeps a bare storage word that carries a statement rather than a path.
    """
    if not prefixes:
        return None
    parts = []
    for prefix in prefixes:
        root = re.escape(prefix.rstrip("/"))
        parts.append(rf"{root}/(?:\.[A-Za-z0-9_-]+/)+")
        parts.append(rf"{root}/(?=[A-Za-z_.])")
    return re.compile("|".join(parts))


class ExportError(RuntimeError):
    pass


def canonical_hash(value: dict[str, Any]) -> str:
    """Same canonical form the source repository uses, so hashes stay comparable."""
    unsigned = dict(value)
    unsigned.pop("content_hash", None)
    payload = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExportError(f"cannot read {path}: {exc}") from exc


def dump_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_commit(source: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ExportError(f"cannot read source commit from {source}: {exc}") from exc


class Rules:
    """The strip rules, read from the source contract instead of hardcoded here."""

    def __init__(self, contract: dict[str, Any]) -> None:
        self.contract = contract
        self.bundles: list[str] = contract["export_scope"]["bundles"]
        self.excluded_files: set[str] = set()
        # Left empty on purpose: the host name to redact is instance data and
        # comes from the contract, not from this file.
        self.host_match: str | None = None
        self.host_replacement = "redacted-host"
        self.path_prefixes = re.compile(r"(?!)")
        self.repository_replacement = "private composition repository"
        self.repository_fields: set[str] = {"repository"}
        self.strip_keys: set[str] = set()

        for rule in contract["strip_rules"]:
            action = rule["action"]
            if action in {"exclude-file", "exclude"}:
                self.excluded_files.update(rule.get("targets", []))
            elif action == "replace-value":
                self.host_match = rule["match"]
                self.host_replacement = rule["replacement"]
            elif action == "replace-field":
                self.repository_replacement = rule["fields"]["provenance.repository"]
                # Every field that carries the private repository name, not just
                # the one in provenance.
                self.repository_fields = {
                    key.rsplit(".", 1)[-1]
                    for key, value in rule["fields"].items()
                    if value == self.repository_replacement
                }
            elif action == "strip-field":
                self.strip_keys.update(rule["fields"])
            elif action == "rewrite-path":
                match = rule["match"]
                prefixes = [match] if isinstance(match, str) else list(match)
                pattern = path_prefix_pattern(prefixes)
                if pattern is not None:
                    self.path_prefixes = pattern

    def rewrite_text(self, text: str) -> str:
        text = self.path_prefixes.sub("", text)                  # S7
        if self.host_match:                                      # S5
            text = text.replace(self.host_match, self.host_replacement)
        return text


def transform(node: Any, rules: Rules) -> Any:
    """Apply the value-level rules recursively.

    Components explicitly marked ``export_projection.public == "excluded"`` in the
    source are dropped here (rule S2). The marker itself never reaches the export;
    what is kept needs no marker, and what is dropped is gone.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in rules.strip_keys:              # S8: unresolvable decision ids
                continue
            if key == "export_projection":           # internal bookkeeping
                continue
            if key in rules.repository_fields and isinstance(value, str):
                out[key] = rules.repository_replacement   # S6, wherever it appears
                continue
            out[key] = transform(value, rules)
        return out
    if isinstance(node, list):
        kept = []
        for item in node:
            if isinstance(item, dict):
                marker = item.get("export_projection")
                if isinstance(marker, dict) and marker.get("public") == "excluded":
                    continue
                path = item.get("path")
                if isinstance(path, str) and path in rules.excluded_files:
                    continue
            kept.append(transform(item, rules))
        return kept
    if isinstance(node, str):
        return rules.rewrite_text(node)
    return node


def export_manifest(raw: dict[str, Any], rules: Rules) -> dict[str, Any]:
    manifest = transform(raw, rules)
    manifest["content_hash"] = canonical_hash(manifest)
    return manifest


def repin(values: dict[str, dict[str, Any]]) -> None:
    """Re-pin cross references to the hashes of the exported forms.

    Without this a reader would verify an exported manifest against a hash that
    belongs to the unexported original and conclude, wrongly, that it was
    tampered with.
    """
    for _ in range(12):
        by_id = {v["id"]: canonical_hash(v) for v in values.values() if v.get("id")}
        by_path = {p: canonical_hash(v) for p, v in values.items()}
        changed = False

        def walk(node: Any) -> None:
            nonlocal changed
            if isinstance(node, dict):
                ref, path = node.get("ref"), node.get("path")
                if "content_hash" in node:
                    target = None
                    if isinstance(ref, str) and ref in by_id:
                        target = by_id[ref]
                    elif isinstance(path, str) and path in by_path:
                        target = by_path[path]
                    if target and node["content_hash"] != target:
                        node["content_hash"] = target
                        changed = True
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        for value in values.values():
            walk(value)
        for value in values.values():
            value["content_hash"] = canonical_hash(value)
        if not changed:
            return
    raise ExportError("hash re-pinning did not converge")


def build(source: Path) -> dict[str, str]:
    """Return the full set of files this export produces, path -> text."""
    contract = read_json(source / CONTRACT_PATH)
    rules = Rules(contract)

    files: dict[str, str] = {}
    values: dict[str, dict[str, Any]] = {}
    provenance: list[dict[str, str]] = []

    for bundle_id in rules.bundles:
        rel_src = f"manifests/bundles/{bundle_id}/bundle.v1.json"
        src = source / rel_src
        if not src.is_file():
            raise ExportError(f"bundle in scope but missing at source: {rel_src}")
        rel_out = f"manifests/bundles/{bundle_id}/bundle.v1.json"
        values[rel_out] = export_manifest(read_json(src), rules)
        provenance.append({"exported_path": rel_out, "source_path": rel_src,
                           "source_sha256": source_sha256(src)})

    # Contracts the exported bundles pin. A recipe without its contract is a
    # dangling reference, so they travel with it.
    wanted: set[str] = set()
    for value in values.values():
        for item in value.get("functional_contracts", []):
            path = item.get("path")
            if isinstance(path, str) and path not in rules.excluded_files:
                wanted.add(path)
    for rel_src in sorted(wanted):
        src = source / rel_src
        if not src.is_file():
            raise ExportError(f"pinned contract missing at source: {rel_src}")
        # Keep the source layout: the bundles pin these by repo-root-relative
        # path, so moving them would turn a valid pin into a dangling one.
        rel_out = rel_src
        values[rel_out] = export_manifest(read_json(src), rules)
        provenance.append({"exported_path": rel_out, "source_path": rel_src,
                           "source_sha256": source_sha256(src)})

    # Catalogue excerpt: the exported bundles only.
    cat_rel = "manifests/bundles.catalog.v1.json"
    catalog = transform(read_json(source / cat_rel), rules)
    in_scope = set(rules.bundles)
    catalog["bundles"] = [b for b in catalog.get("bundles", []) if b.get("id") in in_scope]
    if isinstance(catalog.get("provenance"), dict):
        catalog["provenance"]["repository"] = rules.repository_replacement
    # bundle_classes and pillars are definitional prose about the classification,
    # not per-class entries. They are kept whole: without them the class and
    # pillar fields on each entry have nothing to be read against.
    catalog["export_note"] = (
        "Excerpt. The source catalogue carries every bundle; this one carries the "
        "exported subset, so a reader is not pointed at recipes that are not here."
    )
    values[cat_rel] = catalog
    provenance.append({"exported_path": cat_rel, "source_path": cat_rel,
                       "source_sha256": source_sha256(source / cat_rel)})

    repin(values)

    receipt = {
        "schema": "ellmos.open-ocean-export-receipt.v1",
        "id": "open-ocean-export-receipt",
        "source_repository": rules.repository_replacement,
        "source_commit": source_commit(source),
        "export_contract": CONTRACT_PATH,
        "export_contract_sha256": source_sha256(source / CONTRACT_PATH),
        "rules_applied": [r["id"] for r in contract["strip_rules"]],
        "bundle_count": len(rules.bundles),
        "files": sorted(provenance, key=lambda item: item["exported_path"]),
        "reproducibility": (
            "Deliberately free of timestamps: re-running the export against the same "
            "source commit must produce a byte-identical result, so drift is visible."
        ),
    }
    receipt["content_hash"] = canonical_hash(receipt)
    values["manifests/export-receipt.v1.json"] = receipt

    for rel, value in values.items():
        files[rel] = dump_json(value)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=os.environ.get(SOURCE_ENV),
                        help=f"checkout of the composition source; or set ${SOURCE_ENV}")
    parser.add_argument("--check", action="store_true",
                        help="report drift instead of writing; exit 1 when it differs")
    args = parser.parse_args()

    if args.source is None:
        raise SystemExit(f"--source is required (or set ${SOURCE_ENV})")
    source = Path(args.source).resolve()
    if not (source / CONTRACT_PATH).is_file():
        raise SystemExit(f"no export contract at {source / CONTRACT_PATH}")

    files = build(source)

    drift = [rel for rel, text in files.items()
             if not (ROOT / rel).is_file()
             or (ROOT / rel).read_text(encoding="utf-8") != text]
    if args.check:
        if drift:
            print("export drift:")
            for rel in sorted(drift):
                print(f"  {rel}")
            print("run tools/export_from_source.py to refresh")
            return 1
        print(f"export is current ({len(files)} files)")
        return 0

    for rel, text in files.items():
        out = ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
    print(f"exported {len(files)} files from {source} "
          f"({'updated ' + str(len(drift)) if drift else 'no change'})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
