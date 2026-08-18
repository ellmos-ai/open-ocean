#!/usr/bin/env python3
"""Resolve bundle references from the skeleton into a flat, verified component plan.

This is the "Resolve" and "Verify" steps from architecture/INSTALLER-TARGET.md,
built because they were the #1 documented gap blocking everything else
(INSTALLER-REUSE-BEFUND_2026-08-07.md Sec. 6.4, point 1: "Kein Beteiligter kennt
'Bundle enthaelt Komponenten'"). It reads recipes, it never writes one -- the
recipe repository (`bundles`) stays the sole source of truth and is never
copied into this repository (architecture/open-ocean.skeleton.v1.json,
"any copy of the manifests" is listed under not_yet_present on purpose).

What this script does (INSTALLER-TARGET.md "Resolve" + "Verify"):
  1. Load the skeleton's pinned bundle_refs (ring 1, ring 2, or both).
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

Exit codes: 0 = resolved, all hashes verified. 2 = a hash verification failed.
3 = the skeleton or a referenced bundle manifest could not be read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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


class ResolveError(RuntimeError):
    """A skeleton or bundle manifest could not be read (exit 3)."""


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


def verify_bundle(bundle_ref: dict[str, Any], bundles_root: Path) -> tuple[VerifyResult, dict[str, Any] | None]:
    ref_id = bundle_ref["ref"]
    manifest_path = bundles_root / "manifests" / "bundles" / ref_id / "bundle.v1.json"
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


def resolve_module(component: ResolvedComponent, catalog_path: Path) -> None:
    module_id = component.ref.split(":", 1)[1]
    if not catalog_path.is_file():
        component.status = "unresolved"
        component.detail = {"reason": f"modules.catalog.json not found at {catalog_path}"}
        return
    catalog = read_json(catalog_path)
    modules = {m["id"]: m for m in catalog.get("modules", [])}
    match = modules.get(module_id)
    if match is None:
        ci_matches = [m for mid, m in modules.items() if mid.casefold() == module_id.casefold()]
        match = ci_matches[0] if len(ci_matches) == 1 else None
    if match is None:
        component.status = "unresolved"
        component.detail = {
            "reason": "no catalog entry for this exact or case-insensitive module ID",
            "hint": "the bundle component ref and the catalog ID may have drifted "
                    "(e.g. hyphenation) -- check modules.catalog.json by hand",
        }
        return
    sot = match.get("source_of_truth", {})
    resolved_source = match.get("resolved_source")
    local_path = (catalog_path.parent / resolved_source) if resolved_source else None
    present_locally = bool(local_path and local_path.is_dir())
    component.status = "resolved" if present_locally else "unresolved"
    component.detail = {
        "catalog_id": match["id"], "repository": sot.get("repository"),
        "source_type": sot.get("type"), "resolved_source": resolved_source,
        "present_locally": present_locally, "visibility": match.get("visibility"),
    }


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
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [f"open-ocean resolve report -- ring {report['ring']}", ""]
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
                        help="path to a local checkout of ellmos-ai/bundles")
    parser.add_argument("--ring", default="1", help="'1', '2', or 'all' (default: 1)")
    parser.add_argument("--skeleton", type=Path, default=DEFAULT_SKELETON)
    parser.add_argument("--modules-catalog", type=Path, default=DEFAULT_MODULES_CATALOG)
    parser.add_argument("--skills-registry", type=Path, default=DEFAULT_SKILLS_REGISTRY)
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of text")
    parser.add_argument("--report", type=Path, help="also write the JSON report to this path")
    parser.add_argument("--activation-check", metavar="HOST",
                        help="also run the read-only Activate-readiness check against this host "
                             "adapter (see host_adapters.known_adapters(); e.g. 'claude-code')")
    args = parser.parse_args(argv)

    try:
        skeleton = load_skeleton(args.skeleton)
        refs = select_bundle_refs(skeleton, args.ring)
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
        report = build_report(verifications, [], args.ring)
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_text_report(report))
        print("\nVerify FAILED -- stopping before resolving components (INSTALLER-TARGET.md: "
              "a failed hash check stops the run).", file=sys.stderr)
        return 2

    components = merge_components(component_lists)
    for comp in components:
        if comp.kind == "module":
            resolve_module(comp, args.modules_catalog)
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

    report = build_report(verifications, components, args.ring, activation=activation_summary)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
