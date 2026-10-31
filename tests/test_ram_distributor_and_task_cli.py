# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""Unit tests for RAMDistributor (#1949, #2027, #2028, #2152, #2334, #2419, #2441) and `ocean.py task`."""

from __future__ import annotations

from pathlib import Path

from ocean import main as ocean_main
from ocean_resources import (
    ConsumerCapability,
    DistributorRequest,
    RAMDistributor,
    UserProximity,
    WatchdogHysteresisPolicy,
)


def test_ram_distributor_proximity_inheritance_and_tendency() -> None:
    dist = RAMDistributor(total_ram_bytes=32 * 1024**3, tendency="compute")
    dist.register_consumer(
        ConsumerCapability(
            consumer_id="qwen3.8-27b-mlx",
            kind="model",
            weights_ram_bytes=17 * 1024**3,
            kv_reserve_bytes=3 * 1024**3,
            overhead_bytes=1 * 1024**3,
            fallback_chain=("cloud_router", "defer_with_checkpoint"),
        )
    )
    dist.register_consumer(
        ConsumerCapability(
            consumer_id="blender-render",
            kind="compute",
            weights_ram_bytes=8 * 1024**3,
            kv_reserve_bytes=0,
            overhead_bytes=1 * 1024**3,
            fallback_chain=("defer_with_checkpoint",),
        )
    )

    # Background model vs background compute under 'compute' tendency -> compute wins
    req_bg_model = DistributorRequest(
        request_id="req-buddha",
        consumer_id="qwen3.8-27b-mlx",
        proximity=UserProximity.AUTONOMOUS_BACKGROUND,
        submitted_at=10.0,
    )
    req_bg_compute = DistributorRequest(
        request_id="req-compute",
        consumer_id="blender-render",
        proximity=UserProximity.AUTONOMOUS_BACKGROUND,
        submitted_at=11.0,
    )
    decisions = dist.evaluate(
        [req_bg_model, req_bg_compute],
        available_ram_bytes=22 * 1024**3,
        pressure="normal",
        now=12.0,
    )
    assert decisions[0].request_id == "req-compute"
    assert decisions[0].admitted is True
    assert decisions[1].request_id == "req-buddha"
    assert decisions[1].admitted is False
    assert decisions[1].action == "cloud_router"

    # Interactive user request or child inheriting interactive proximity beats background compute
    req_subagent = DistributorRequest(
        request_id="req-subagent",
        consumer_id="qwen3.8-27b-mlx",
        proximity=UserProximity.AUTONOMOUS_BACKGROUND,
        inherited_from_proximity=UserProximity.DIRECT_INTERACTIVE,
        submitted_at=15.0,
    )
    assert req_subagent.effective_proximity == UserProximity.DELEGATED_FOREGROUND
    decisions2 = dist.evaluate(
        [req_bg_compute, req_subagent],
        available_ram_bytes=28 * 1024**3,
        pressure="normal",
        now=16.0,
    )
    assert decisions2[0].request_id == "req-subagent"
    assert decisions2[0].admitted is True


def test_watchdog_hysteresis_policy_prevents_cold_start_false_alarm() -> None:
    policy = WatchdogHysteresisPolicy()
    # 60s after model load at elevated pressure -> do NOT evict (#2419)
    evict, reason = policy.should_evict_model(
        available_ram_bytes=2 * 1024**3,
        pressure="elevated",
        seconds_since_model_load=60.0,
        sustained_critical_seconds=0.0,
    )
    assert evict is False
    assert reason == "within_cold_start_grace_window"

    # Sustained critical pressure >= 15s -> evict
    evict_crit, reason_crit = policy.should_evict_model(
        available_ram_bytes=1 * 1024**3,
        pressure="critical",
        seconds_since_model_load=120.0,
        sustained_critical_seconds=20.0,
    )
    assert evict_crit is True
    assert reason_crit == "sustained_critical_memory_pressure"


def test_ocean_cli_task_delegates_to_taskplan(tmp_path: Path) -> None:
    db_file = str(tmp_path / "ocean_tasks.db")
    rc = ocean_main(
        [
            "task",
            "take",
            "--new",
            "--title",
            "Ocean CLI Task",
            "--by",
            "gemini@laptop",
            "--db",
            db_file,
            "--json",
        ]
    )
    assert rc == 0
