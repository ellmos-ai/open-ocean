#!/usr/bin/env python3
"""Build the explicit, reviewable BACH-to-OCEAN composition matrix.

The classifier deliberately does not infer equivalence from names.  Each
registered BACH name must be assigned explicitly to one of three outcomes:
``carrier`` (a real catalog/registry carrier exists but still needs binding),
``gap`` (no carrier was found), or ``not-adopted`` (an alias or external
surface is intentionally not an independent module).  The resulting JSON is
an evidence register, not an equivalence or release claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:  # Supports both ``python tools/...`` and package imports in tests.
    from .audit_bach_handlers import audit
except ImportError:  # pragma: no cover - exercised by the documented CLI path
    from audit_bach_handlers import audit


# Every value is a real catalog module or public Skills Registry entry.  The
# locator is intentionally stable and points to the catalog identity rather
# than to an unpinned local implementation checkout.
CARRIERS = {
    "agent agents": "agent-launcher",
    "ati task": "task-master",
    "api apiprober": "ApiProber",
    "backup db dbsync restore sync": "sqlite-transit-sync",
    "bericht": "report-forge",
    "calendar": "assist:assist:kalender",
    "chain routine recurring": "marblerun",
    "scheduler": "ellmos-scheduler",
    "schwarm": "swarm_ai",
    "claude-bridge": "claude-bridge",
    "cloud": "open-compute",
    "clutch": "clutch",
    "connections partner integration": "ellmos-agent-bridge",
    "connector email msg": "connectors",
    "consolidation context doc docs-search search": "GARDENER",
    "contact": "mail-connector",
    "cv": "expert:utilities:bewerbungsexperte",
    "daily-agent": "task-master",
    "denkarium notespace obsidian": "llm-note",
    "dist setup update upgrade startup": "ellmos-installer",
    "docs help": "project-docs-template",
    "fs logs maintain scan status watcher": "system-explorer",
    "gesundheit": "assist:assist:gesundheit",
    "gui theme": "ellmos-unified-gui",
    "haushalt": "assist:assist:haushalt-manager",
    "healthcheck": "system-auditor",
    "hooks inject": "hook-master",
    "lesson mem memory shared-mem": "USMC",
    "literatur": "tool:research:research-agent",
    "media": "ai-media-editor",
    "mount path": "ellmos-core",
    "news newspaper press": "umbruch-social-media-runner",
    "notify": "assistant-core",
    "permissions sandbox": "lock-master",
    "profile": "build-your-users-mind",
    "prompt": "prompt-listener",
    "security settings": "policy-registry",
    "session snapshot": "session-checkpoint",
    "skills": "skill:infrastructure:skill-explorer",
    "sources": "source-resolver",
    "steuer": "steuer-suite",
    "task": "task-master",
    "test tuev usecase": "ellmos-tests",
    "tools": "ellmos-code-tools",
    "versicherung": "assist:assist:finanz-versicherung",
    "web-parse web-scrape": "web-scraper",
    "wiki": "WikiStub-Seed",
}

# No current module/skill carrier was found for these contracts.  The list is
# intentionally conservative: a merely similarly named component is a carrier
# only when its declared catalog capability is relevant.
GAPS = {
    "abo cookbook data extensions lang mcp mediplaner plugins profiler reflection shutdown smarthome "
    "timer tokens trash": "No declared module or Skills Registry carrier for the BACH contract.",
    "clock beat between countdown": "The scheduler has scheduling capabilities, but no timer/countdown contract.",
}

ALIASES = {
    "consolidate": "consolidation",
    "daemon": "scheduler",
    "health": "healthcheck",
    "hook": "hooks",
    "mail": "email",
    "plugin": "plugins",
    "skill": "skills",
    "swarm": "schwarm",
    "tool": "tools",
}

EXTERNAL = {"ollama": "External model runtime; bind as an access surface, not a module."}


def expand(groups: dict[str, str]) -> dict[str, str]:
    return {name: value for names, value in groups.items() for name in names.split()}


def classify(names: list[str]) -> list[dict[str, str]]:
    carriers = expand(CARRIERS)
    gaps = expand(GAPS)
    rows: list[dict[str, str]] = []
    for name in names:
        source = f"BACH registry name {name!r}"
        if name in ALIASES:
            rows.append({"name": name, "class": "not-adopted", "source_locator": source,
                         "target": ALIASES[name], "decision_ref": "D-20260906-003",
                         "binding": "Alias resolves to the canonical target; no independent implementation.",
                         "use_case_state": "not-independent"})
        elif name in EXTERNAL:
            rows.append({"name": name, "class": "not-adopted", "source_locator": source,
                         "target": "access_surface:ollama", "decision_ref": "D-20260906-003",
                         "binding": EXTERNAL[name], "use_case_state": "not-independent"})
        elif name in carriers:
            carrier = carriers[name]
            carrier_type = "skill" if ":" in carrier else "module"
            rows.append({"name": name, "class": "carrier", "source_locator": source,
                         "carrier": carrier, "carrier_locator": f"{carrier_type}:{carrier}",
                         "binding": "Contract, adapter/reintegration, bundle membership and functional use-case evidence remain open.",
                         "use_case_state": "not-evidenced"})
        elif name in gaps:
            rows.append({"name": name, "class": "gap", "source_locator": source,
                         "finding": gaps[name], "use_case_state": "not-evidenced"})
        else:
            raise ValueError(f"No explicit classification for {name}")
    return rows


def load_catalog(path: Path, key: str) -> tuple[dict, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get(key, [])
    if not isinstance(entries, list):
        raise ValueError(f"{path} has no list at {key!r}")
    return payload, entries


def validate_carriers(rows: list[dict[str, str]], modules: list[dict], skills: list[dict]) -> None:
    module_ids = {entry.get("id") for entry in modules}
    skill_ids = {entry.get("id") for entry in skills}
    missing = [
        row["carrier"]
        for row in rows
        if row["class"] == "carrier"
        and row["carrier"] not in (skill_ids if row["carrier_locator"].startswith("skill:") else module_ids)
    ]
    if missing:
        raise ValueError(f"Carrier(s) absent from their declared catalogue: {sorted(set(missing))}")


def fingerprint(path: Path, entries: list[dict]) -> dict[str, object]:
    return {"path": str(path), "entries": len(entries), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bach-root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--module-catalog", type=Path, required=True)
    parser.add_argument("--bundle-catalog", type=Path, required=True)
    parser.add_argument("--skills-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recorded-at", default="2026-09-21")
    args = parser.parse_args()
    source = audit(args.bach_root.resolve())
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    historic_names = baseline["source_audit"]["registered_name_set"]
    historic_set = set(historic_names)
    additions = [name for name in source["registered_names"] if name not in historic_set]
    removals = [name for name in historic_names if name not in set(source["registered_names"])]
    if removals:
        raise ValueError(f"Current registry lost historic names: {removals}")
    rows = classify(source["registered_names"])
    _, modules = load_catalog(args.module_catalog, "modules")
    _, bundles = load_catalog(args.bundle_catalog, "bundles")
    _, skills = load_catalog(args.skills_registry, "components")
    validate_carriers(rows, modules, skills)
    payload = {
        "schema": "ellmos.open-ocean-bach-composition-matrix.v1",
        "recorded_at": args.recorded_at,
        "source_audit": {"bach_commit": "39d2457adeb0bcbcd9f1205dfb2c08f3086b30ed", "counts": source["counts"],
                         "historic_114_names": historic_names, "additions_since_historic_114": additions,
                         "registered_names": source["registered_names"]},
        "catalogues": {"modules": fingerprint(args.module_catalog, modules),
                       "bundles": fingerprint(args.bundle_catalog, bundles),
                       "skills": fingerprint(args.skills_registry, skills)},
        "claim_boundary": "Carrier presence is a composition lead only. It does not prove operation equivalence, state migration, BACH delegation, bundle installation, a foreign-host sluice test, or release parity.",
        "rows": rows,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
