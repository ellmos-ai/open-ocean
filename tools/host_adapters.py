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

Read-only in this slice, deliberately. `skill_present()` is the only check
implemented -- it answers "would Activate have anything to do", not "do it".
Writing a skill into a host (the actual Activate mutation) and its rollback
counterpart are a separate, larger follow-up named in the build plan report:
INSTALLER-TARGET.md's own "must not do" list ("not resolve a recipe it cannot
verify", "roll back on failure") applies with full force to a mutating step,
and deserves its own session rather than being appended to this one.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


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


def known_adapters() -> dict[str, type]:
    """Registry of concrete adapters, by the name resolve_bundles.py's
    --activation-check flag takes. Exactly one entry today; the point of the
    Protocol above is that Codex/Gemini-agy/Kimi can be added here later
    without any caller needing to change (a "vendor-neutral from the start"
    interface names its shape before it has more than one implementation)."""
    return {"claude-code": ClaudeCodeHostAdapter}
