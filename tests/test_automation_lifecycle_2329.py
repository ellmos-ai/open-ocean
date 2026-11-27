# -*- coding: utf-8 -*-
"""Regression and integration tests for shared AutomationLifecycleRegistry (#2329)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.agent_library import (
    AutomationLifecycleRegistry,
    open_workspace_lifecycle_registry,
    read_workspace_automation_lifecycle,
)
from tools.gui_bridge import agent_library_reader


def test_sqlite_persistence_across_restart_and_crud(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "automation_lifecycle.db"
    reg1 = AutomationLifecycleRegistry(db_path=db_path)

    mod_job = reg1.register_entry({
        "id": "module-cleanup-job",
        "title": "Module Cleanup Job",
        "family": "job",
        "trigger": "routine",
        "from_module": True,
        "scheduled": False,
        "timezone": "Europe/Berlin",
    })
    assert mod_job["state"] == "available"
    assert mod_job["fence"] == 1

    with pytest.raises(RuntimeError, match="bestätigter Planung"):
        reg1.trigger_start("module-cleanup-job", start_trigger="routine", dedup_key="run-avail")

    scheduled = reg1.schedule_entry(
        "module-cleanup-job",
        schedule_spec="0 4 * * *",
        expected_fence=mod_job["fence"],
    )
    assert scheduled["state"] == "ready"
    assert scheduled["scheduled"] is True
    assert scheduled["fence"] == 2

    started = reg1.trigger_start("module-cleanup-job", start_trigger="manual", dedup_key="man-001")
    assert started["state"] == "running"
    assert started["deduplicated"] is False
    assert started["fence"] == 3

    # Restart simulation: fresh instance reads persisted state & dedup key
    reg2 = AutomationLifecycleRegistry(db_path=db_path)
    loaded = reg2.get_entry("module-cleanup-job")
    assert loaded["state"] == "running"
    assert loaded["fence"] == 3

    dup = reg2.trigger_start("module-cleanup-job", start_trigger="manual", dedup_key="man-001")
    assert dup["deduplicated"] is True
    assert dup["fence"] == 3

    # Stale fence on update or stop must fail
    with pytest.raises(RuntimeError, match="Fence-Konflikt"):
        reg2.stop_entry("module-cleanup-job", expected_fence=2)
    with pytest.raises(RuntimeError, match="Fence-Konflikt"):
        reg2.update_entry("module-cleanup-job", {"title": "Wrong Fence"}, expected_fence=2)
    with pytest.raises(RuntimeError, match="vor dem Löschen gestoppt"):
        reg2.delete_entry("module-cleanup-job", expected_fence=3)

    stopped = reg2.stop_entry("module-cleanup-job", expected_fence=3)
    assert stopped["state"] == "ready"
    assert stopped["fence"] == 4

    updated = reg2.update_entry("module-cleanup-job", {"title": "Updated Cleanup Job"}, expected_fence=4)
    assert updated["title"] == "Updated Cleanup Job"
    assert updated["fence"] == 5

    assert [e["id"] for e in reg2.list_entries(family="job", state="ready")] == ["module-cleanup-job"]

    deleted = reg2.delete_entry("module-cleanup-job", expected_fence=5)
    assert deleted == {"deleted": True, "id": "module-cleanup-job", "fence": 5}
    assert AutomationLifecycleRegistry(db_path=db_path).list_entries() == []


def test_family_invariants_and_timezone_validation(tmp_path: Path) -> None:
    reg = AutomationLifecycleRegistry(db_path=tmp_path / "lifecycle.db")

    with pytest.raises(ValueError, match="Sprachmodell"):
        reg.register_entry({"id": "bad-job", "family": "job", "trigger": "routine", "requires_model": True})

    with pytest.raises(ValueError, match="input_schema"):
        reg.register_entry({"id": "bad-mini-1", "family": "mini_agent", "trigger": "event"})

    with pytest.raises(ValueError, match="offene Agentenarbeit"):
        reg.register_entry({
            "id": "bad-mini-2",
            "family": "mini_agent",
            "trigger": "event",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "allows_reviews": True,
        })

    with pytest.raises(ValueError, match="Ungültige Zeitzone"):
        reg.register_entry({
            "id": "bad-tz",
            "family": "automation_agent",
            "trigger": "routine",
            "timezone": "Mars/Olympus_Mons",
        })


def test_calendar_binding_bidirectional_sync_and_dst_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "lifecycle.db"
    reg = AutomationLifecycleRegistry(db_path=db_path)

    reg.register_entry({
        "id": "mod-calendar-agent",
        "family": "automation_agent",
        "trigger": "calendar_once",
        "from_module": True,
        "scheduled": False,
        "timezone": "Europe/Berlin",
    })
    binding = reg.bind_calendar_event(
        "mod-calendar-agent",
        calendar_event_id="cal-evt-42",
        scheduled_at="2026-07-15T09:00:00+02:00",
        sync_direction="bidirectional",
    )
    assert binding["status"] == "scheduled"
    assert binding["tz_offset"] == "+0200"
    assert reg.get_entry("mod-calendar-agent")["state"] == "ready"

    # External calendar cancellation keeps base entry intact and marks binding cancelled
    cancelled = reg.cancel_calendar_event(
        "mod-calendar-agent",
        calendar_event_id="cal-evt-42",
        source="calendar",
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled_by"] == "calendar"
    assert reg.get_entry("mod-calendar-agent")["state"] == "ready"

    # One-way binding blocks external calendar cancel
    reg.register_entry({
        "id": "oneway-agent",
        "family": "automation_agent",
        "trigger": "calendar_once",
        "timezone": "Europe/Berlin",
    })
    reg.bind_calendar_event(
        "oneway-agent",
        calendar_event_id="cal-evt-99",
        scheduled_at="2026-12-10T09:00:00Z",
        sync_direction="to_calendar",
    )
    with pytest.raises(PermissionError, match="to_calendar"):
        reg.cancel_calendar_event("oneway-agent", calendar_event_id="cal-evt-99", source="calendar")

    started_oneway = reg.trigger_start(
        "oneway-agent",
        start_trigger="calendar_once",
        dedup_key="cal-99",
        tz_now=datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc),
    )
    assert started_oneway["tz_offset"] == "+0100"
    reg.stop_entry("oneway-agent", expected_fence=started_oneway["fence"])
    assert reg.list_calendar_bindings("oneway-agent", status="executed")[0]["calendar_event_id"] == "cal-evt-99"

    # Routine agent triggered manually -> run grouped under actual start_trigger 'manual'
    reg.register_entry({
        "id": "routine-reporter",
        "family": "automation_agent",
        "trigger": "routine",
        "timezone": "Europe/Berlin",
    })
    summer_run = reg.trigger_start(
        "routine-reporter",
        start_trigger="manual",
        dedup_key="manual-1",
        tz_now=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
    )
    assert summer_run["tz_offset"] == "+0200"
    reg.stop_entry("routine-reporter", expected_fence=summer_run["fence"])

    grouped = AutomationLifecycleRegistry(db_path=db_path).list_runs(group_by_trigger=True)
    assert [r["entry_id"] for r in grouped["manual"]] == ["routine-reporter"]
    assert grouped["manual"][0]["configured_trigger"] == "routine"
    assert [r["entry_id"] for r in grouped["calendar_once"]] == ["oneway-agent"]
    assert grouped["routine"] == []


def test_workspace_helper_and_gui_bridge_agent_library_integration(tmp_path: Path) -> None:
    empty_snap = read_workspace_automation_lifecycle(tmp_path)
    assert empty_snap["available"] is False
    assert empty_snap["entries"] == []

    reg = open_workspace_lifecycle_registry(tmp_path)
    reg.register_entry({
        "id": "mini-tagger",
        "family": "mini_agent",
        "trigger": "event",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    })
    catalog = agent_library_reader(tmp_path)()
    assert catalog["automation_lifecycle"]["available"] is True
    assert [e["id"] for e in catalog["automation_lifecycle"]["entries"]] == ["mini-tagger"]
