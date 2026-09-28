#!/usr/bin/env python3
"""S8 Skills- and Workflow-Projection tool for open-ocean.

Projects declarative skills from a skills registry and modules from a modules
catalog into verified, human- and machine-readable Markdown files:
  - SKILLS.md: All declared skills, statuses, requirements, and metadata
  - MODULES.md: All declared modules, statuses, requirements, and metadata
  - TOOLCHAINS.md: (optional) Toolchain definitions and execution index

Reuses tools.resolve_bundles as a library for component resolution, schema
validation, and cryptographic content hashing.

Usage:
    python tools/project_workflows.py --skills-registry <path>
        --modules-catalog <path> --output-dir <path>
        [--db-path <path>] [--include-toolchains]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from tools.resolve_bundles import (
        DEFAULT_MODULES_CATALOG,
        DEFAULT_SKILLS_REGISTRY,
        ResolvedComponent,
        canonical_hash,
        expand_components,
        load_component_bindings,
        merge_components,
        resolve_module,
        resolve_skill,
    )
except ImportError:
    from resolve_bundles import (  # type: ignore
        DEFAULT_MODULES_CATALOG,
        DEFAULT_SKILLS_REGISTRY,
        ResolvedComponent,
        canonical_hash,
        expand_components,
        load_component_bindings,
        merge_components,
        resolve_module,
        resolve_skill,
    )


class ProjectWorkflowsError(RuntimeError):
    """Raised when an input registry, catalog, or database cannot be read or validated."""


def read_json(path: Path) -> Any:
    """Read and decode JSON file fail-closed."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectWorkflowsError(f"cannot read JSON from {path}: {exc}") from exc


def _clean_cell(value: Any) -> str:
    """Format a value safely for a Markdown table cell."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "-"
        return ", ".join(str(v).strip() for v in value).replace("|", "\\|")
    text = str(value).strip().replace("\n", " ").replace("\r", "").replace("|", "\\|")
    return text if text else "-"


@dataclass
class ProjectionResult:
    """Outcome of projecting skills, modules, and toolchains."""

    skills: list[ResolvedComponent] = field(default_factory=list)
    modules: list[ResolvedComponent] = field(default_factory=list)
    toolchains: list[dict[str, Any]] = field(default_factory=list)
    written_files: list[Path] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "skills": [s.as_dict() for s in self.skills],
            "modules": [m.as_dict() for m in self.modules],
            "toolchains": self.toolchains,
            "written_files": [str(p) for p in self.written_files],
        }


def load_skills_from_registry(registry_path: Path) -> tuple[list[ResolvedComponent], Any]:
    """Read skills from a skills registry and resolve each component."""
    if not registry_path.is_file():
        raise ProjectWorkflowsError(f"skills registry not found at {registry_path}")

    raw_data = read_json(registry_path)
    entries: list[dict[str, Any]] = []

    if isinstance(raw_data, dict):
        if "components" in raw_data and isinstance(raw_data["components"], list):
            entries = raw_data["components"]
        elif "skills" in raw_data and isinstance(raw_data["skills"], list):
            entries = raw_data["skills"]
        elif "skills" in raw_data and isinstance(raw_data["skills"], dict):
            for key, val in raw_data["skills"].items():
                if isinstance(val, dict):
                    entry = dict(val)
                    entry.setdefault("name", key.split(":")[-1])
                    entries.append(entry)
    elif isinstance(raw_data, list):
        entries = raw_data

    components: list[ResolvedComponent] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            raw_id = entry.get("id", "")
            name = raw_id.split(":")[-1] if raw_id else None
        if not name:
            continue

        ref = f"skill:{name}"
        req = entry.get("requirement", "unspecified")
        bundles = entry.get("bundles") or entry.get("from_bundles") or []
        if isinstance(bundles, str):
            bundles = [bundles]

        comp = ResolvedComponent(
            ref=ref,
            kind="skill",
            requirement=req,
            from_bundles=list(bundles),
        )
        resolve_skill(comp, registry_path)
        components.append(comp)

    components.sort(key=lambda c: c.ref)
    return components, raw_data


def load_modules_from_catalog(
    catalog_path: Path,
    component_bindings: dict[str, Any] | None = None,
) -> tuple[list[ResolvedComponent], Any]:
    """Read modules from a modules catalog and resolve each component."""
    if not catalog_path.is_file():
        raise ProjectWorkflowsError(f"modules catalog not found at {catalog_path}")

    raw_data = read_json(catalog_path)
    entries: list[dict[str, Any]] = []

    if isinstance(raw_data, dict):
        if "modules" in raw_data and isinstance(raw_data["modules"], list):
            entries = raw_data["modules"]
    elif isinstance(raw_data, list):
        entries = raw_data

    components: list[ResolvedComponent] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        mod_id = entry.get("id")
        if not mod_id:
            continue

        ref = f"module:{mod_id}"
        req = entry.get("requirement", "unspecified")
        bundles = entry.get("bundles") or entry.get("from_bundles") or []
        if isinstance(bundles, str):
            bundles = [bundles]

        comp = ResolvedComponent(
            ref=ref,
            kind="module",
            requirement=req,
            from_bundles=list(bundles),
        )
        resolve_module(comp, catalog_path, component_bindings)
        components.append(comp)

    components.sort(key=lambda c: c.ref)
    return components, raw_data


def load_toolchains_from_db(db_path: Path) -> tuple[list[dict[str, Any]], Any]:
    """Read toolchain definitions from a toolchain database JSON file."""
    if not db_path.is_file():
        raise ProjectWorkflowsError(f"toolchain database not found at {db_path}")

    raw_data = read_json(db_path)
    toolchains: list[dict[str, Any]] = []

    if isinstance(raw_data, list):
        toolchains = [item for item in raw_data if isinstance(item, dict)]
    elif isinstance(raw_data, dict):
        if "toolchains" in raw_data and isinstance(raw_data["toolchains"], list):
            toolchains = [item for item in raw_data["toolchains"] if isinstance(item, dict)]
        else:
            for key, val in raw_data.items():
                if isinstance(val, dict):
                    item = dict(val)
                    item.setdefault("id", key)
                    toolchains.append(item)

    toolchains.sort(key=lambda t: str(t.get("id", "")))
    return toolchains, raw_data


def project_bundle_components(manifests: list[dict[str, Any]]) -> list[ResolvedComponent]:
    """Expand and merge components across multiple bundle manifests."""
    component_lists: list[list[ResolvedComponent]] = []
    for manifest in manifests:
        bundle_id = manifest.get("id", "unnamed-bundle")
        component_lists.append(expand_components(manifest, bundle_id))
    return merge_components(component_lists)


def render_skills_markdown(
    skills: list[ResolvedComponent],
    registry_path: Path | None = None,
    registry_hash: str | None = None,
) -> str:
    """Render SKILLS.md documentation."""
    lines: list[str] = [
        "# Skills Projection",
        "",
        "S8 Projection of declared skills against the registry.",
        "",
    ]
    if registry_path:
        lines.append(f"- **Source Registry**: `{registry_path.name}`")
    if registry_hash:
        lines.append(f"- **Content Hash**: `{registry_hash}`")
    lines.append(f"- **Total Skills**: {len(skills)}")
    resolved_count = sum(1 for s in skills if s.status == "resolved")
    lines.append(f"- **Resolved**: {resolved_count}")
    lines.append(f"- **Unresolved**: {len(skills) - resolved_count}")
    lines.append("")

    lines.append("## Overview Table")
    lines.append("")
    lines.append("| Component Ref | Status | Requirement | Source Bundles | Registry ID | Category | Path |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")

    for s in skills:
        det = s.detail or {}
        ref_cell = f"`{s.ref}`"
        status_cell = s.status
        req_cell = s.requirement
        bundles_cell = _clean_cell(s.from_bundles)
        reg_id_cell = _clean_cell(det.get("registry_id"))
        cat_cell = _clean_cell(det.get("category"))
        path_cell = _clean_cell(det.get("path"))
        lines.append(
            f"| {ref_cell} | {status_cell} | {req_cell} | {bundles_cell} | {reg_id_cell} | {cat_cell} | {path_cell} |"
        )

    lines.append("")
    lines.append("## Component Details")
    lines.append("")

    for s in skills:
        lines.append(f"### `{s.ref}`")
        lines.append(f"- **Status**: `{s.status}`")
        lines.append(f"- **Requirement**: `{s.requirement}`")
        bundles_str = _clean_cell(s.from_bundles)
        lines.append(f"- **Source Bundles**: {bundles_str}")

        det = s.detail or {}
        if det.get("registry_id"):
            lines.append(f"- **Registry ID**: `{det['registry_id']}`")
        if det.get("category"):
            lines.append(f"- **Category**: `{det['category']}`")
        if det.get("path"):
            lines.append(f"- **Path**: `{det['path']}`")
        if det.get("reason"):
            lines.append(f"- **Reason**: {det['reason']}")
        if det.get("note"):
            lines.append(f"- **Note**: {det['note']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_modules_markdown(
    modules: list[ResolvedComponent],
    catalog_path: Path | None = None,
    catalog_hash: str | None = None,
) -> str:
    """Render MODULES.md documentation."""
    lines: list[str] = [
        "# Modules Projection",
        "",
        "S8 Projection of declared modules against the catalog.",
        "",
    ]
    if catalog_path:
        lines.append(f"- **Source Catalog**: `{catalog_path.name}`")
    if catalog_hash:
        lines.append(f"- **Content Hash**: `{catalog_hash}`")
    lines.append(f"- **Total Modules**: {len(modules)}")
    resolved_count = sum(1 for m in modules if m.status == "resolved")
    lines.append(f"- **Resolved**: {resolved_count}")
    lines.append(f"- **Unresolved**: {len(modules) - resolved_count}")
    lines.append("")

    lines.append("## Overview Table")
    lines.append("")
    lines.append("| Component Ref | Status | Requirement | Source Bundles | Kind | Visibility | Repository |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")

    for m in modules:
        det = m.detail or {}
        ref_cell = f"`{m.ref}`"
        status_cell = m.status
        req_cell = m.requirement
        bundles_cell = _clean_cell(m.from_bundles)
        kind_cell = _clean_cell(det.get("kind"))
        vis_cell = _clean_cell(det.get("visibility"))
        repo_cell = _clean_cell(det.get("repository"))
        lines.append(
            f"| {ref_cell} | {status_cell} | {req_cell} | {bundles_cell} | {kind_cell} | {vis_cell} | {repo_cell} |"
        )

    lines.append("")
    lines.append("## Component Details")
    lines.append("")

    for m in modules:
        lines.append(f"### `{m.ref}`")
        lines.append(f"- **Status**: `{m.status}`")
        lines.append(f"- **Requirement**: `{m.requirement}`")
        bundles_str = _clean_cell(m.from_bundles)
        lines.append(f"- **Source Bundles**: {bundles_str}")

        det = m.detail or {}
        if det.get("catalog_id"):
            lines.append(f"- **Catalog ID**: `{det['catalog_id']}`")
        if det.get("kind"):
            lines.append(f"- **Kind**: `{det['kind']}`")
        if det.get("visibility"):
            lines.append(f"- **Visibility**: `{det['visibility']}`")
        if det.get("repository"):
            lines.append(f"- **Repository**: `{det['repository']}`")
        if det.get("source_type"):
            lines.append(f"- **Source Type**: `{det['source_type']}`")
        if det.get("resolved_source"):
            lines.append(f"- **Resolved Source**: `{det['resolved_source']}`")
        if "present_locally" in det:
            lines.append(f"- **Present Locally**: `{det['present_locally']}`")
        if det.get("provides"):
            lines.append(f"- **Provides**: {_clean_cell(det['provides'])}")
        if det.get("requires"):
            lines.append(f"- **Requires**: {_clean_cell(det['requires'])}")
        if det.get("reason"):
            lines.append(f"- **Reason**: {det['reason']}")
        if det.get("hint"):
            lines.append(f"- **Hint**: {det['hint']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_toolchains_markdown(
    toolchains: list[dict[str, Any]],
    db_path: Path | None = None,
    db_hash: str | None = None,
) -> str:
    """Render TOOLCHAINS.md documentation."""
    lines: list[str] = [
        "# Toolchains Index",
        "",
        "S8 Projection of declared toolchains from the toolchain database.",
        "",
    ]
    if db_path:
        lines.append(f"- **Source Database**: `{db_path.name}`")
    if db_hash:
        lines.append(f"- **Content Hash**: `{db_hash}`")
    lines.append(f"- **Total Toolchains**: {len(toolchains)}")
    lines.append("")

    lines.append("## Overview Table")
    lines.append("")
    lines.append("| ID | Name | Trigger | Status | Steps |")
    lines.append("| --- | --- | --- | --- | --- |")

    for tc in toolchains:
        tc_id = _clean_cell(tc.get("id"))
        tc_name = _clean_cell(tc.get("name"))
        trigger = _clean_cell(tc.get("trigger") or tc.get("trigger_type"))
        is_active = tc.get("is_active")
        if is_active is None:
            status = _clean_cell(tc.get("status"))
        else:
            status = "active" if is_active else "inactive"
        steps_val = tc.get("steps") or tc.get("steps_json")
        step_count = len(steps_val) if isinstance(steps_val, list) else 1 if steps_val else 0
        lines.append(f"| `{tc_id}` | {tc_name} | {trigger} | {status} | {step_count} |")

    lines.append("")
    lines.append("## Toolchain Details")
    lines.append("")

    for tc in toolchains:
        tc_id = tc.get("id", "unnamed")
        tc_name = tc.get("name", "")
        lines.append(f"### `{tc_id}`: {tc_name}" if tc_name else f"### `{tc_id}`")
        if tc.get("description"):
            lines.append(f"- **Description**: {tc['description']}")
        trigger = tc.get("trigger") or tc.get("trigger_type")
        if trigger:
            lines.append(f"- **Trigger**: `{trigger}`")
        if "is_active" in tc:
            lines.append(f"- **Active**: `{tc['is_active']}`")
        elif "status" in tc:
            lines.append(f"- **Status**: `{tc['status']}`")

        steps = tc.get("steps") or tc.get("steps_json")
        if isinstance(steps, list) and steps:
            lines.append("- **Steps**:")
            for idx, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    step_str = step.get("name") or step.get("action") or json.dumps(step)
                else:
                    step_str = str(step)
                lines.append(f"  {idx}. `{step_str}`")
        elif steps:
            lines.append(f"- **Steps**: `{steps}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def project_workflows(
    skills_registry: Path | str = DEFAULT_SKILLS_REGISTRY,
    modules_catalog: Path | str = DEFAULT_MODULES_CATALOG,
    db_path: Path | str | None = None,
    output_dir: Path | str = Path("."),
    include_toolchains: bool = False,
    *,
    component_bindings_path: Path | str | None = None,
) -> dict[str, Any]:
    """Resolve and project skills, modules, and optional toolchains to Markdown files.

    Writes:
      - <output_dir>/SKILLS.md
      - <output_dir>/MODULES.md
      - <output_dir>/TOOLCHAINS.md (when include_toolchains=True)

    Returns a dictionary summarizing the projected components and written files.
    """
    skills_reg_path = Path(skills_registry).resolve()
    modules_cat_path = Path(modules_catalog).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    bindings_manifest: dict[str, Any] | None = None
    if component_bindings_path is not None:
        bindings_manifest = load_component_bindings(Path(component_bindings_path).resolve())

    # 1. Skills
    skills, raw_skills = load_skills_from_registry(skills_reg_path)
    skills_hash = canonical_hash(raw_skills) if isinstance(raw_skills, dict) else None
    skills_md = render_skills_markdown(skills, skills_reg_path, skills_hash)
    skills_path = out_dir / "SKILLS.md"
    skills_path.write_text(skills_md, encoding="utf-8")

    # 2. Modules
    modules, raw_modules = load_modules_from_catalog(modules_cat_path, bindings_manifest)
    modules_hash = canonical_hash(raw_modules) if isinstance(raw_modules, dict) else None
    modules_md = render_modules_markdown(modules, modules_cat_path, modules_hash)
    modules_path = out_dir / "MODULES.md"
    modules_path.write_text(modules_md, encoding="utf-8")

    written = [skills_path, modules_path]
    toolchains: list[dict[str, Any]] = []

    # 3. Toolchains (optional)
    if include_toolchains:
        if not db_path:
            raise ProjectWorkflowsError("--include-toolchains requires --db-path")
        db_p = Path(db_path).resolve()
        toolchains, raw_db = load_toolchains_from_db(db_p)
        db_hash = canonical_hash(raw_db) if isinstance(raw_db, dict) else None
        toolchains_md = render_toolchains_markdown(toolchains, db_p, db_hash)
        toolchains_path = out_dir / "TOOLCHAINS.md"
        toolchains_path.write_text(toolchains_md, encoding="utf-8")
        written.append(toolchains_path)

    result = ProjectionResult(
        skills=skills,
        modules=modules,
        toolchains=toolchains,
        written_files=written,
    )
    return result.as_dict()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="S8 projection tool for skills, modules, and workflows.",
    )
    parser.add_argument(
        "--skills-registry",
        type=Path,
        default=DEFAULT_SKILLS_REGISTRY,
        help=f"Path to skills registry JSON (default: {DEFAULT_SKILLS_REGISTRY})",
    )
    parser.add_argument(
        "--modules-catalog",
        type=Path,
        default=DEFAULT_MODULES_CATALOG,
        help=f"Path to modules catalog JSON (default: {DEFAULT_MODULES_CATALOG})",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to toolchains database JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory where SKILLS.md, MODULES.md (and TOOLCHAINS.md) will be written",
    )
    parser.add_argument(
        "--include-toolchains",
        action="store_true",
        default=False,
        help="Include toolchains index in projection (requires --db-path)",
    )
    parser.add_argument(
        "--component-bindings",
        type=Path,
        default=None,
        help="Optional path to component-bindings JSON overlay",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        res = project_workflows(
            skills_registry=args.skills_registry,
            modules_catalog=args.modules_catalog,
            db_path=args.db_path,
            output_dir=args.output_dir,
            include_toolchains=args.include_toolchains,
            component_bindings_path=args.component_bindings,
        )
        print(
            f"Successfully projected {len(res['skills'])} skills and "
            f"{len(res['modules'])} modules"
            + (f" and {len(res['toolchains'])} toolchains" if args.include_toolchains else "")
            + f" to {args.output_dir}"
        )
        return 0
    except ProjectWorkflowsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
