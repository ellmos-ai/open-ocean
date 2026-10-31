"""Project core and installed module documentation from ellmos.module.v2 manifests (#2459)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

DOC_PRECEDENCE = (
    "user_decision",
    "transformation_plan",
    "module_documentation",
    "core_documentation",
)


def extract_manifest_docs(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the optional `docs` block of an ellmos.module.v2 manifest."""
    raw_docs = manifest.get("docs")
    if isinstance(raw_docs, dict):
        entry = str(raw_docs.get("entry") or "README.md")
        langs = raw_docs.get("languages")
        if not isinstance(langs, list) or not langs:
            langs = ["de", "en"]
        else:
            langs = [str(x) for x in langs if isinstance(x, str) and x.strip()]
    else:
        entry = "README.md"
        langs = ["de", "en"]
    return {
        "id": str(manifest.get("id") or manifest.get("name") or "unknown"),
        "version": str(manifest.get("version") or "0.0.0"),
        "entry": entry,
        "languages": langs,
        "surfaces": list(manifest.get("surfaces") or []),
    }


def project_installed_module_help(workspace_root: Path) -> Dict[str, Any]:
    """Scan installed module manifests under workspace_root and return the /help projection."""
    root = Path(workspace_root)
    modules: List[Dict[str, Any]] = []
    for manifest_path in sorted(root.rglob("ellmos-module.v2.json")) + sorted(root.rglob("MANIFEST.json")):
        if ".git" in manifest_path.parts or "node_modules" in manifest_path.parts:
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or not (data.get("id") or data.get("name")):
            continue
        item = extract_manifest_docs(data)
        item["manifest_path"] = str(manifest_path.relative_to(root)).replace("\\", "/")
        modules.append(item)
    return {
        "schema": "ellmos.open-ocean.help-projection.v1",
        "precedence": list(DOC_PRECEDENCE),
        "core_doc": "docs/CORE.md" if (root / "docs/CORE.md").is_file() else None,
        "skill_doc": "SKILL.md" if (root / "SKILL.md").is_file() else None,
        "modules": modules,
    }
