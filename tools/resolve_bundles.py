#!/usr/bin/env python3
"""Resolve bundle references from a skeleton or system manifest into a verified component plan.

This is the "Resolve" and "Verify" steps from architecture/INSTALLER-TARGET.md,
built because they were the #1 documented gap blocking everything else
(INSTALLER-REUSE-BEFUND_2026-08-07.md Sec. 6.4, point 1: "Kein Beteiligter kennt
'Bundle enthaelt Komponenten'"). It reads recipes, it never writes one -- the
recipe repository (`bundles`) stays the sole source of truth and is never
copied into this repository (architecture/open-ocean.skeleton.v1.json,
"any copy of the manifests" is listed under not_yet_present on purpose).

What this script does (INSTALLER-TARGET.md "Resolve" + "Verify"):
  1. Load pinned bundle_refs from either the public skeleton (ring 1, ring 2,
     or both) or an external ellmos.system.v1 composition (all refs).
  2. For each bundle: read its bundle.v1.json from an external --bundles-root
     checkout, recompute its content_hash the same way the recipe repository
     computes it (bundles/tools/export_from_source.py:canonical_hash -- sorted,
     compact JSON, sha256, self-referential field excluded), and compare that
     against both the file's own declared content_hash and the value pinned in
     the skeleton. A mismatch is a Verify failure and stops the run with a
     non-zero exit code (INSTALLER-TARGET.md: "A failed hash check stops the
     run; it does not warn and continue").
  3. Expand each bundle's `components[]` into a flat, de-duplicated list.
  4. Apply `choice_groups[]` at the default_selection only -- this is the
     minimal, already-legitimate reading of an existing field (not the general
     min/max choice-applier INSTALLER-REUSE-BEFUND Sec. 6.4 point 2 flags as
     separately missing; that stays a named follow-up).
  5. Classify and resolve each component by kind:
       module:<id>          -> .MODULES/_scripts/module_resolver.py's catalog
                                (modules.catalog.json), same lookup logic
       skill:<name>          -> the canonical public ellmos-ai/skills registry,
                                matched by `name` (the skills crosswalk file the
                                component-registry-bindings contract names,
                                manifests/skills.registry.crosswalk.v1.json, does
                                not exist in the bundles checkout yet -- documented
                                as a follow-up, not silently assumed)
       access_surface:<id>   -> reported, never fetched (INSTALLER-TARGET.md
                                "Not fetch access surfaces" -- commercial
                                providers are reached through their own CLI/app)

Deliberately NOT this script's job (INSTALLER-TARGET.md "Fetch"/"Place"/
"Activate"/"Roll back" are separate steps, and the write-side ones are a larger,
separately scoped follow-up -- see the ocean-dev build plan report):
  - cloning or copying anything
  - writing into any host agent CLI's configuration
  - mutating modules.catalog.json, the skills registry, or any bundle manifest

Usage:
    python tools/resolve_bundles.py --bundles-root <path-to-bundles-checkout>
        [--ring 1|2|all] [--skeleton <path>] [--modules-catalog <path>]
        [--skills-registry <path>] [--json] [--report <path>]

    python tools/resolve_bundles.py --bundles-root <path-to-recipe-projection>
        --system-manifest <path-to-system.v1.json>

Exit codes: 0 = resolved, all hashes verified. 2 = a hash verification failed.
3 = the composition or a referenced bundle manifest could not be read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Makes `import host_adapters` resolve regardless of how this file is invoked
# (`python tools/resolve_bundles.py ...` puts tools/ on sys.path[0] already;
# `python -m unittest` / `from tools.resolve_bundles import ...` puts the repo
# root there instead, which does NOT include tools/ -- add it explicitly so
# both paths work without two different import spellings).
sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKELETON = REPO_ROOT / "architecture" / "open-ocean.skeleton.v1.json"
# .MODULES/_scripts lives in OneDrive, not in this repository -- an external
# pointer like --bundles-root, not a vendored copy.
DEFAULT_MODULES_CATALOG = Path.home() / "OneDrive" / ".TOPICS" / ".AI" / ".MODULES" / "modules.catalog.json"
DEFAULT_SKILLS_REGISTRY = Path.home() / "OneDrive" / ".TOPICS" / ".AI" / ".SKILLS" / "registry" / "components.json"
DEFAULT_COMPONENT_BINDINGS = REPO_ROOT / "architecture" / "ocean-full-dev.component-bindings.v1.json"
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ResolveError(RuntimeError):
    """A composition or bundle manifest could not be read (exit 3)."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResolveError(f"cannot read {path}: {exc}") from exc


def canonical_hash(value: dict[str, Any]) -> str:
    """Same algorithm as bundles/tools/export_from_source.py:canonical_hash,
    duplicated deliberately rather than imported: this repository must stay
    readable and runnable without a sibling checkout of the recipe repo on
    PYTHONPATH (--bundles-root is a data pointer, not an import path)."""
    unsigned = dict(value)
    unsigned.pop("content_hash", None)
    payload = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_repository(value: str) -> str:
    return value.strip().rstrip("/").removesuffix(".git").casefold()


def load_component_bindings(path: Path | None) -> dict[str, Any]:
    """Load the exact OCEAN integration crosswalk.

    The file is deliberately an integration overlay, not a component registry:
    each entry points one already-declared bundle reference at one native module
    catalog record and one immutable provider commit.  No fuzzy, case-folded, or
    semantic alias inference is permitted here.
    """
    if path is None:
        return {"bindings": {}}
    manifest = read_json(path)
    if manifest.get("schema") != "ellmos.open-ocean-component-bindings.v1":
        raise ResolveError(f"{path} has an unsupported component-binding schema")
    if manifest.get("authority") != {
        "kind": "integration-overlay",
        "runtime_authority": False,
    }:
        raise ResolveError(
            f"{path} must remain a non-runtime integration overlay"
        )
    if not isinstance(manifest.get("id"), str) or not manifest["id"].strip():
        raise ResolveError(f"{path} has no non-empty id")
    if manifest.get("version") != "1.0.0":
        raise ResolveError(f"{path} has an unsupported version")
    expected_hash = manifest.get("content_hash")
    computed_hash = canonical_hash(manifest)
    if expected_hash != computed_hash:
        raise ResolveError(
            f"{path} content_hash mismatch: declared {expected_hash!r}, "
            f"computed {computed_hash}"
        )
    bindings = manifest.get("bindings")
    if not isinstance(bindings, dict):
        raise ResolveError(f"{path} bindings must be an object")
    allowed_fields = {
        "component_type",
        "catalog_id",
        "repository",
        "commit",
        "placement_id",
        "required_provides",
        "provider_manifest",
    }
    for ref, binding in bindings.items():
        if not isinstance(ref, str) or not ref.startswith("module:"):
            raise ResolveError(f"{path} binding reference is not an exact module ref: {ref!r}")
        if not isinstance(binding, dict) or set(binding) != allowed_fields:
            raise ResolveError(f"{path} binding {ref!r} has unsupported or missing fields")
        if binding.get("component_type") != "module":
            raise ResolveError(f"{path} binding {ref!r} must have component_type=module")
        for field_name in ("catalog_id", "repository", "placement_id"):
            if not isinstance(binding.get(field_name), str) or not binding[field_name].strip():
                raise ResolveError(f"{path} binding {ref!r} has no non-empty {field_name}")
        if ref != f"module:{binding['placement_id']}":
            raise ResolveError(
                f"{path} binding {ref!r} placement_id must preserve the declared reference"
            )
        if not _GIT_SHA_RE.fullmatch(str(binding.get("commit", ""))):
            raise ResolveError(f"{path} binding {ref!r} has no full lowercase commit SHA")
        required = binding.get("required_provides")
        if (
            not isinstance(required, list)
            or not required
            or any(not isinstance(item, str) or not item for item in required)
            or required != sorted(set(required))
        ):
            raise ResolveError(f"{path} binding {ref!r} has invalid required_provides")
        if binding.get("provider_manifest") != "ellmos-module.v2.json":
            raise ResolveError(
                f"{path} binding {ref!r} must verify ellmos-module.v2.json"
            )
    return manifest


def component_bindings_summary(
    manifest: dict[str, Any], components: list[ResolvedComponent],
) -> dict[str, Any] | None:
    bindings = manifest.get("bindings") or {}
    if not bindings:
        return None
    applied = sorted(
        component.ref for component in components if component.detail.get("binding")
    )
    return {
        "schema": manifest.get("schema"),
        "id": manifest.get("id"),
        "content_hash": manifest.get("content_hash"),
        "applied_refs": applied,
    }


@dataclass
class VerifyResult:
    bundle_ref: str
    manifest_path: str
    pinned_hash: str
    declared_hash: str | None
    computed_hash: str | None
    self_consistent: bool  # declared_hash == computed_hash (file not tampered/corrupt)
    matches_pin: bool      # declared_hash == pinned_hash (skeleton not stale)
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_ref": self.bundle_ref, "manifest_path": self.manifest_path,
            "pinned_hash": self.pinned_hash, "declared_hash": self.declared_hash,
            "computed_hash": self.computed_hash, "self_consistent": self.self_consistent,
            "matches_pin": self.matches_pin, "ok": self.ok,
        }


@dataclass
class ResolvedComponent:
    ref: str                  # e.g. "module:USMC", "skill:decide"
    kind: str                 # module | skill | access_surface
    from_bundles: list[str] = field(default_factory=list)
    requirement: str = "unspecified"  # required | recommended | optional (highest across bundles wins)
    from_choice: str | None = None  # set if this ref came from a choice_group default, not a hard component
    status: str = "unresolved"      # resolved | unresolved | not-fetched-by-design
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref, "kind": self.kind, "from_bundles": self.from_bundles,
            "requirement": self.requirement, "from_choice": self.from_choice,
            "status": self.status, "detail": self.detail,
        }


# INSTALLER-TARGET.md doesn't rank requirement levels, but a merge across
# bundles needs a total order to pick one when the same component is
# "required" in one bundle and "optional" in another -- required wins.
_REQUIREMENT_RANK = {"required": 0, "recommended": 1, "optional": 2, "unspecified": 3}


def load_skeleton(skeleton_path: Path) -> dict[str, Any]:
    skeleton = read_json(skeleton_path)
    if skeleton.get("authority", {}).get("runtime_authority") is not False:
        raise ResolveError(
            f"{skeleton_path} does not declare authority.runtime_authority=false -- "
            "refusing to treat an unexpected schema as the skeleton"
        )
    return skeleton


def load_system_manifest(system_path: Path) -> dict[str, Any]:
    system = read_json(system_path)
    if system.get("schema") != "ellmos.system.v1":
        raise ResolveError(
            f"{system_path} is not an ellmos.system.v1 manifest"
        )
    if system.get("authority", {}).get("runtime_authority") is not False:
        raise ResolveError(
            f"{system_path} does not declare authority.runtime_authority=false -- "
            "refusing to treat it as a declarative system composition"
        )
    if not isinstance(system.get("id"), str) or not system["id"].strip():
        raise ResolveError(f"{system_path} has no non-empty id")
    if not isinstance(system.get("bundle_refs"), list) or not system["bundle_refs"]:
        raise ResolveError(f"{system_path} has no non-empty bundle_refs[] list")
    seen_refs: set[str] = set()
    for index, bundle_ref in enumerate(system["bundle_refs"]):
        if not isinstance(bundle_ref, dict):
            raise ResolveError(f"{system_path} bundle_refs[{index}] is not an object")
        for key in ("ref", "content_hash"):
            if not isinstance(bundle_ref.get(key), str) or not bundle_ref[key].strip():
                raise ResolveError(
                    f"{system_path} bundle_refs[{index}] has no non-empty {key}"
                )
        if bundle_ref["ref"] in seen_refs:
            raise ResolveError(
                f"{system_path} has duplicate bundle ref {bundle_ref['ref']!r}"
            )
        seen_refs.add(bundle_ref["ref"])
    return system


def select_bundle_refs(skeleton: dict[str, Any], ring: str) -> list[dict[str, Any]]:
    all_refs = {r["ref"]: r for r in skeleton.get("bundle_refs", [])}
    if ring == "all":
        return list(all_refs.values())
    rings = skeleton.get("rings", {})
    ring_def = rings.get(ring)
    if ring_def is None:
        raise ResolveError(f"ring {ring!r} not found in skeleton (have: {sorted(rings)})")
    missing = [m for m in ring_def["members"] if m not in all_refs]
    if missing:
        raise ResolveError(f"ring {ring} names bundles not in bundle_refs[]: {missing}")
    return [all_refs[m] for m in ring_def["members"]]


def load_bundle_selection(
    *, skeleton_path: Path | None, system_path: Path | None, ring: str | None,
) -> tuple[list[dict[str, Any]], str, dict[str, str] | None]:
    """Load one composition authority and return refs, selection, and safe metadata."""
    if skeleton_path is not None and system_path is not None:
        raise ResolveError("--skeleton and --system-manifest are mutually exclusive")
    if system_path is not None:
        if ring not in (None, "all"):
            raise ResolveError(
                "--system-manifest is a complete composition; only --ring all is valid"
            )
        composition = load_system_manifest(system_path)
        selection = "all"
        metadata = {
            "mode": "system-manifest",
            "schema": composition["schema"],
            "id": composition["id"],
        }
    else:
        composition = load_skeleton(skeleton_path or DEFAULT_SKELETON)
        selection = ring or "1"
        metadata = None
    return select_bundle_refs(composition, selection), selection, metadata


def verify_bundle(bundle_ref: dict[str, Any], bundles_root: Path) -> tuple[VerifyResult, dict[str, Any] | None]:
    ref_id = bundle_ref["ref"]
    exported_path = bundles_root / "manifests" / "bundles" / ref_id / "bundle.v1.json"
    private_projection_path = bundles_root / "bundles" / ref_id / "bundle.v1.json"
    exported_exists = exported_path.is_file()
    private_projection_exists = private_projection_path.is_file()
    if exported_exists and private_projection_exists:
        raise ResolveError(
            f"ambiguous bundle manifest for {ref_id!r}: both {exported_path} "
            f"and {private_projection_path} exist"
        )
    manifest_path = private_projection_path if private_projection_exists else exported_path
    pinned = bundle_ref["content_hash"]
    if not manifest_path.is_file():
        return VerifyResult(ref_id, str(manifest_path), pinned, None, None, False, False, False), None
    manifest = read_json(manifest_path)
    declared = manifest.get("content_hash")
    computed = canonical_hash(manifest)
    self_consistent = declared == computed
    matches_pin = declared == pinned
    return VerifyResult(
        ref_id, str(manifest_path), pinned, declared, computed,
        self_consistent, matches_pin, ok=self_consistent and matches_pin,
    ), manifest


def expand_components(manifest: dict[str, Any], bundle_ref: str) -> list[ResolvedComponent]:
    """Component entries carry a NESTED ref: {"type": "module", "ref": {"ref":
    "module:x", "version": "..."}, "requirement": "recommended", ...} -- the
    outer `ref` key is a wrapper, the actual "<kind>:<name>" string lives one
    level deeper at ref["ref"]["ref"]. Verified empirically against all five
    ring-1 bundle manifests before writing this, not assumed from the schema
    docs alone (the schema names weren't self-evident: `type` duplicates the
    kind prefix, and `ref` is reused for both the wrapper and the inner id)."""
    out: list[ResolvedComponent] = []
    for comp in manifest.get("components", []) or []:
        inner = comp.get("ref")
        ref = inner.get("ref") if isinstance(inner, dict) else inner
        if not isinstance(ref, str):
            raise ResolveError(f"{bundle_ref}: component entry has no resolvable ref: {comp!r}")
        kind = comp.get("type") or ref.split(":", 1)[0]
        out.append(ResolvedComponent(
            ref=ref, kind=kind, from_bundles=[bundle_ref],
            requirement=comp.get("requirement", "unspecified"),
        ))
    for group in manifest.get("choice_groups", []) or []:
        defaults = group.get("default_selection") or []
        for cand in group.get("candidates", []):
            if cand.get("ref") not in defaults:
                continue
            identity = cand.get("identity") or f"{cand.get('type', 'module')}:{cand['ref']}"
            kind = identity.split(":", 1)[0]
            out.append(ResolvedComponent(
                ref=identity, kind=kind, from_bundles=[bundle_ref], from_choice=group["id"],
                requirement="required",  # a chosen default IS the bundle's answer for that role
            ))
    return out


def merge_components(component_lists: list[list[ResolvedComponent]]) -> list[ResolvedComponent]:
    merged: dict[str, ResolvedComponent] = {}
    for comps in component_lists:
        for c in comps:
            if c.ref in merged:
                existing = merged[c.ref]
                for b in c.from_bundles:
                    if b not in existing.from_bundles:
                        existing.from_bundles.append(b)
                if c.from_choice and not existing.from_choice:
                    existing.from_choice = c.from_choice
                if _REQUIREMENT_RANK[c.requirement] < _REQUIREMENT_RANK[existing.requirement]:
                    existing.requirement = c.requirement
            else:
                merged[c.ref] = c
    return [merged[k] for k in sorted(merged)]


def resolve_module(
    component: ResolvedComponent,
    catalog_path: Path,
    component_bindings: dict[str, Any] | None = None,
) -> None:
    binding = (component_bindings or {}).get("bindings", {}).get(component.ref)
    module_id = binding["catalog_id"] if binding else component.ref.split(":", 1)[1]
    if not catalog_path.is_file():
        component.status = "unresolved"
        component.detail = {"reason": f"modules.catalog.json not found at {catalog_path}"}
        return
    catalog = read_json(catalog_path)
    modules = {m["id"]: m for m in catalog.get("modules", [])}
    match = modules.get(module_id)
    if match is None and binding is None:
        ci_matches = [m for mid, m in modules.items() if mid.casefold() == module_id.casefold()]
        match = ci_matches[0] if len(ci_matches) == 1 else None
    if match is None:
        component.status = "unresolved"
        component.detail = {
            "reason": (
                "no catalog entry for the exact bound provider ID"
                if binding
                else "no catalog entry for this exact or case-insensitive module ID"
            ),
            "hint": (
                "component bindings never infer aliases; refresh the explicit binding or catalog"
                if binding
                else "the bundle component ref and the catalog ID may have drifted "
                     "(e.g. hyphenation) -- check modules.catalog.json by hand"
            ),
        }
        return
    sot = match.get("source_of_truth", {})
    resolved_source = match.get("resolved_source")
    local_path = (catalog_path.parent / resolved_source) if resolved_source else None
    present_locally = bool(local_path and local_path.is_dir())
    binding_detail = None
    repository_matches = True
    if binding:
        repository_matches = _normalized_repository(str(sot.get("repository") or "")) == (
            _normalized_repository(binding["repository"])
        )
        binding_detail = {
            **binding,
            "overlay_id": component_bindings.get("id"),
            "provider_verified": False,
        }
    component.status = (
        "unresolved" if binding else "resolved" if present_locally else "unresolved"
    )
    component.detail = {
        "catalog_id": match["id"], "repository": sot.get("repository"),
        "source_type": sot.get("type"), "resolved_source": resolved_source,
        "local_path": str(local_path.resolve(strict=False)) if local_path else None,
        "present_locally": present_locally if binding is None else False,
        "visibility": match.get("visibility"),
        "kind": match.get("kind"), "package": match.get("package"),
        "provides": list(match.get("provides") or []),
        "requires": list(match.get("requires") or []),
        "entrypoints": dict(match.get("entrypoints") or {}),
        "boundaries": dict(match.get("boundaries") or {}),
    }
    if binding_detail is not None:
        component.detail["catalog_present_locally"] = present_locally
        component.detail["binding"] = binding_detail
        component.detail["catalog_repository_matches_binding"] = repository_matches
        if not repository_matches:
            component.status = "unresolved"
            component.detail["reason"] = (
                "catalog repository does not match the exact component binding repository"
            )
        else:
            component.detail["reason"] = (
                "bound provider awaits exact Fetch/Place verification in the OCEAN workspace"
            )


def resolve_skill(component: ResolvedComponent, registry_path: Path) -> None:
    name = component.ref.split(":", 1)[1]
    if not registry_path.is_file():
        component.status = "unresolved"
        component.detail = {"reason": f"skills registry not found at {registry_path}"}
        return
    registry = read_json(registry_path)
    entries = registry.get("components", registry) if isinstance(registry, dict) else registry
    matches = [e for e in entries if e.get("name") == name]
    if not matches:
        component.status = "unresolved"
        component.detail = {
            "reason": "no registry entry with this exact name",
            "note": "matched by name, not the id field (bundle refs use skill:<name>, "
                    "the registry's own id is skill:<category>:<name>); the crosswalk file "
                    "the component-registry-bindings contract names "
                    "(manifests/skills.registry.crosswalk.v1.json) does not exist yet "
                    "in the bundles checkout -- see the build plan follow-ups",
        }
        return
    entry = matches[0]
    component.status = "resolved"
    component.detail = {
        "registry_id": entry.get("id"), "category": entry.get("category"),
        "status": entry.get("status"), "path": entry.get("path"),
    }


def resolve_access_surface(component: ResolvedComponent) -> None:
    component.status = "not-fetched-by-design"
    component.detail = {
        "reason": "access surfaces are commercial providers/APIs reached through their own "
                  "CLI or app; INSTALLER-TARGET.md is explicit that the installer must not "
                  "fetch them -- the recipe declares the dependency, nothing more",
    }


def apply_activation_check(components: list[ResolvedComponent], adapter: Any) -> dict[str, Any]:
    """Read-only slice of "Activate" (INSTALLER-TARGET.md): for every resolved
    skill component, ask the host adapter whether it is already usable there.
    Mutates each component's `detail["activation"]`; returns a summary. Only
    `skill:` components are checked -- HostAdapter has no module-activation
    method yet (modules "activate" by being importable/clonable, which the
    Resolve step's module status already answers; a host-specific module
    activation concept, if one turns out to be needed, is a follow-up)."""
    checked = 0
    present = 0
    for comp in components:
        if comp.kind != "skill" or comp.status != "resolved":
            continue
        name = comp.ref.split(":", 1)[1]
        is_present = adapter.skill_present(name)
        comp.detail["activation"] = {"host": adapter.name, "present": is_present}
        checked += 1
        present += int(is_present)
    return {"host": adapter.name, "skills_checked": checked, "skills_present": present}


def build_report(
    verifications: list[VerifyResult], components: list[ResolvedComponent], ring: str,
    activation: dict[str, Any] | None = None,
    composition: dict[str, str] | None = None,
) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for c in components:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    report: dict[str, Any] = {
        "schema": "ellmos.open-ocean-resolve-report.v1",
        "ring": ring,
        "verify": {
            "bundles_checked": len(verifications),
            "all_ok": all(v.ok for v in verifications),
            "results": [v.as_dict() for v in verifications],
        },
        "components": {
            "total": len(components),
            "by_status": by_status,
            "resolved": [c.as_dict() for c in components],
        },
    }
    if activation is not None:
        report["activation"] = activation
    if composition is not None:
        report["composition"] = composition
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [f"open-ocean resolve report -- ring {report['ring']}", ""]
    if "composition" in report:
        composition = report["composition"]
        lines.extend([
            f"Composition: {composition['mode']} {composition['id']} "
            f"({composition['schema']})",
            "",
        ])
    v = report["verify"]
    lines.append(f"Verify: {v['bundles_checked']} bundle(s) checked, all_ok={v['all_ok']}")
    for r in v["results"]:
        mark = "OK" if r["ok"] else "FAIL"
        lines.append(f"  [{mark}] {r['bundle_ref']}: self_consistent={r['self_consistent']} matches_pin={r['matches_pin']}")
    lines.append("")
    c = report["components"]
    lines.append(f"Components: {c['total']} total, by status: {c['by_status']}")
    for comp in c["resolved"]:
        choice_note = f" (choice default of {comp['from_choice']})" if comp["from_choice"] else ""
        act = comp["detail"].get("activation")
        act_note = f" [{act['host']}: {'present' if act['present'] else 'NOT present'}]" if act else ""
        lines.append(
            f"  [{comp['status']:>20}] ({comp['requirement']:>11}) {comp['ref']}"
            f"{choice_note}{act_note} <- {', '.join(comp['from_bundles'])}"
        )
    if "activation" in report:
        a = report["activation"]
        lines.append("")
        lines.append(f"Activate (read-only check, host={a['host']}): "
                     f"{a['skills_present']}/{a['skills_checked']} skills already present")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundles-root", type=Path, required=True,
                        help="path to a bundle export checkout or private recipe projection")
    parser.add_argument("--ring", help="'1', '2', or 'all' (default: 1 for the skeleton; "
                        "system manifests always select all refs)")
    parser.add_argument("--skeleton", type=Path)
    parser.add_argument("--system-manifest", type=Path,
                        help="ellmos.system.v1 composition; selects every bundle_ref")
    parser.add_argument("--modules-catalog", type=Path, default=DEFAULT_MODULES_CATALOG)
    parser.add_argument("--skills-registry", type=Path, default=DEFAULT_SKILLS_REGISTRY)
    parser.add_argument(
        "--component-bindings",
        type=Path,
        default=DEFAULT_COMPONENT_BINDINGS,
        help="exact OCEAN integration overlay for declared component aliases",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of text")
    parser.add_argument("--report", type=Path, help="also write the JSON report to this path")
    parser.add_argument("--activation-check", metavar="HOST",
                        help="also run the read-only Activate-readiness check against this host "
                             "adapter (see host_adapters.known_adapters(); e.g. 'claude-code')")
    args = parser.parse_args(argv)

    try:
        component_bindings = load_component_bindings(args.component_bindings)
        refs, selection, composition_metadata = load_bundle_selection(
            skeleton_path=args.skeleton,
            system_path=args.system_manifest,
            ring=args.ring,
        )
    except ResolveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    verifications: list[VerifyResult] = []
    component_lists: list[list[ResolvedComponent]] = []
    for bundle_ref in refs:
        try:
            result, manifest = verify_bundle(bundle_ref, args.bundles_root)
        except ResolveError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        verifications.append(result)
        if result.ok and manifest is not None:
            component_lists.append(expand_components(manifest, bundle_ref["ref"]))

    if not all(v.ok for v in verifications):
        report = build_report(
            verifications, [], selection, composition=composition_metadata,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_text_report(report))
        print("\nVerify FAILED -- stopping before resolving components (INSTALLER-TARGET.md: "
              "a failed hash check stops the run).", file=sys.stderr)
        return 2

    components = merge_components(component_lists)
    for comp in components:
        if comp.kind == "module":
            resolve_module(comp, args.modules_catalog, component_bindings)
        elif comp.kind == "skill":
            resolve_skill(comp, args.skills_registry)
        elif comp.kind == "access_surface":
            resolve_access_surface(comp)
        else:
            comp.status = "unresolved"
            comp.detail = {"reason": f"unknown component kind: {comp.kind!r}"}

    activation_summary = None
    if args.activation_check:
        from host_adapters import known_adapters
        adapters = known_adapters()
        adapter_cls = adapters.get(args.activation_check)
        if adapter_cls is None:
            print(f"ERROR: unknown --activation-check host {args.activation_check!r} "
                 f"(known: {sorted(adapters)})", file=sys.stderr)
            return 3
        activation_summary = apply_activation_check(components, adapter_cls())

    report = build_report(
        verifications, components, selection, activation=activation_summary,
        composition=composition_metadata,
    )
    bindings_summary = component_bindings_summary(component_bindings, components)
    if bindings_summary is not None:
        report["component_bindings"] = bindings_summary
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
