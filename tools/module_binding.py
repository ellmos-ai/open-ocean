"""Exact binding of one composed module to its directory (shared by the lifecycle and the GUI bridge)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bound_module_dir(component: Any, catalog_id: str, modules_root: Path) -> Path:
    """The module directory if ``component`` is exactly the composed ``module:<catalog_id>`` entry, else ValueError.

    The final path (symlinks and junctions resolved) must be the module's own directory directly below the composition's
    modules folder, so a configuration can neither point the reader at an arbitrary path nor escape through a link.
    """
    detail = component.get("detail") if isinstance(component, dict) else None
    if (not isinstance(detail, dict) or component.get("kind") != "module" or component.get("ref") != f"module:{catalog_id}"
            or detail.get("catalog_id") != catalog_id):
        raise ValueError("not-the-composed-module")
    raw = detail.get("local_path")
    if not isinstance(raw, str) or not raw or "\0" in raw:
        raise ValueError("no-local-path")
    resolved = Path(raw).resolve(strict=False)
    if resolved.parent != Path(modules_root).resolve(strict=False) or resolved.name != catalog_id:
        raise ValueError("outside-the-modules-folder")
    return resolved
