"""Vendor-neutral host-adapter abstraction for the "Activate" step of
architecture/INSTALLER-TARGET.md.

INSTALLER-TARGET.md names this the step with no package-manager equivalent
("the target is an agent, not a filesystem") and lists as an open question
whether the installer targets one host agent CLI, several, or an abstraction
over them. This module answers that: an abstraction (`HostAdapter`), with
exactly one concrete implementation for now.

Precedent this follows: D-20260817-005 ("controlroom" E4, Multi-Agent-
Reichweite, ENTSCHIEDEN [B, Claude als Referenz]) -- vendor-neutral from the
start, Claude Code as the reference implementation. That decision was made for
a different interface (controlroom); it is applied here because the ocean-dev
build plan names it as the governing precedent for all new interfaces in this
programme, not because this module re-litigates it.

`skill_present()` stayed read-only through the first slice; this one adds the
write side (`activate_skill`) and its rollback counterpart
(`rollback_activate_skill`). Both carry a safety rule that has nothing to do
with git-pin correctness and everything to do with not surprising the person
running this tool: **the constructor never defaults `skills_dir` to a host's
real, live skill directory for write purposes.** `skill_present()`'s own
default (`~/.claude/skills`) is unchanged and still fine -- it only reads.
The caller that wires up a *write*-capable adapter (tools/ocean_dev.py) is
responsible for passing an explicit `skills_dir`, normally a subdirectory of
its own `--workspace`, never the bare default; ocean_dev.py's own default is
`<workspace>/skills`, not `~/.claude/skills`. That is a calling-convention
rule, not something this module can enforce by itself, since the same class
still needs to support the read-only check against the real directory too.

`activate_skill` never overwrites: an existing destination is a no-op
("skipped-exists"), matching the same "never overwrite" policy
tools/fetch_place.py uses for module destinations (with that reasoning:
rollback that simply removes what it created is trivially correct exactly
because the write side never destroys anything that existed before it ran --
an *update* path, if one is ever wanted, needs its own snapshot-based design
and is out of scope here, same as BACH's update.py rollback backs up before
ever overwriting: system/hub/update.py's `_apply()`/`_rollback()` is the
phase-model precedent this activate/rollback pair follows -- back up (here:
"only ever write into empty space") before mutating, so undo is exact).
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_place import force_rmtree  # noqa: E402  -- shared Windows-readonly-safe rmtree, see its docstring


@runtime_checkable
class HostAdapter(Protocol):
    """What any agent-CLI host must be able to answer for the Activate step's
    read-only readiness check. A future write-side Activate would extend this
    with `activate_skill`/`activate_module` plus a rollback counterpart."""

    name: str

    def skill_present(self, skill_name: str) -> bool:
        """True if `skill_name` is already usable on this host, i.e. Activate
        would have nothing to do for it."""
        ...


@dataclass
class ActivateResult:
    skill_name: str
    action: str              # activated | skipped-exists | failed | planned
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"skill_name": self.skill_name, "action": self.action, "detail": self.detail}


class ClaudeCodeHostAdapter:
    """Reference implementation (E4: "Claude als Referenz"). Presence = a
    directory of that name exists under the host's skills directory -- the
    same shallow check a human would make, not a manifest/version parse
    (SKILL.md's own frontmatter is a separate, richer question this slice
    does not need)."""

    name = "claude-code"

    def __init__(self, skills_dir: Path | None = None) -> None:
        self.skills_dir = skills_dir or (Path.home() / ".claude" / "skills")

    def skill_present(self, skill_name: str) -> bool:
        return (self.skills_dir / skill_name).is_dir()

    def activate_skill(self, skill_name: str, source_dir: Path, *, apply: bool) -> ActivateResult:
        """Copy `source_dir` (the skill's own directory, containing SKILL.md)
        to `self.skills_dir / skill_name`. Never overwrites an existing
        destination -- see the "never overwrite" note in this module's
        docstring. `apply=False` reports what would happen without touching
        the filesystem at all (not even creating skills_dir)."""
        dest = self.skills_dir / skill_name
        if dest.exists():
            return ActivateResult(skill_name, "skipped-exists", {"dest": str(dest)})
        if not source_dir.is_dir():
            return ActivateResult(skill_name, "failed", {"reason": f"source directory not found: {source_dir}"})
        if not apply:
            return ActivateResult(skill_name, "planned", {"source": str(source_dir), "dest": str(dest)})
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(source_dir, dest)
        except OSError as exc:
            force_rmtree(dest)
            return ActivateResult(skill_name, "failed", {"reason": str(exc)})
        if not dest.is_dir():
            return ActivateResult(skill_name, "failed", {"reason": "copytree reported success but dest is missing"})
        return ActivateResult(skill_name, "activated", {"source": str(source_dir), "dest": str(dest)})

    def rollback_activate_skill(self, skill_name: str) -> ActivateResult:
        """Removes `self.skills_dir / skill_name`. Callers must only invoke
        this for a skill_name their own run actually activated (tracked in an
        activation log, e.g. tools/ocean_dev.py's) -- this method has no way
        of knowing on its own whether the directory pre-existed, by design:
        that bookkeeping is policy, and belongs with the caller that decided
        to apply in the first place, not duplicated into the mechanism."""
        dest = self.skills_dir / skill_name
        if not dest.is_dir():
            return ActivateResult(skill_name, "failed", {"reason": f"nothing to roll back at {dest}"})
        force_rmtree(dest)
        return ActivateResult(skill_name, "rolled-back", {"dest": str(dest)})


def known_adapters() -> dict[str, type]:
    """Registry of concrete adapters, by the name resolve_bundles.py's
    --activation-check flag takes. Exactly one entry today; the point of the
    Protocol above is that Codex/Gemini-agy/Kimi can be added here later
    without any caller needing to change (a "vendor-neutral from the start"
    interface names its shape before it has more than one implementation)."""
    return {"claude-code": ClaudeCodeHostAdapter}
