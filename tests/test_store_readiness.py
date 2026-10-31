# -*- coding: utf-8 -*-
"""Tests for Windows Store Readiness Checker (Task #2497)."""
from tools.store_readiness import evaluate_windows_store_readiness


def _valid_msix(**overrides):
    base = {
        "identity_name": "EllmosAI.OpenOcean",
        "publisher": "CN=EllmosAI",
        "version": "0.1.0.0",
        "processor_architecture": "x64",
        "executable": "open-ocean-desktop.exe",
    }
    base.update(overrides)
    return base


def _valid_listing(**overrides):
    base = {
        "display_name": "Open-Ocean Desktop",
        "short_description": "Local AI Agent Studio & Governance Workbench",
        "privacy_policy_url": "https://ellmos.ai/privacy",
        "age_rating_questionnaire_completed": True,
        "screenshots": ["assets/store/living-board.png", "assets/store/running-board.png"],
    }
    base.update(overrides)
    return base


def test_windows_store_readiness_complete_and_user_gated():
    res = evaluate_windows_store_readiness(
        _valid_msix(),
        _valid_listing(),
        wack_passed=True,
        authenticode_signed=True,
    )
    assert res["msix_ready"] is True
    assert res["listing_ready"] is True
    assert res["wack_passed"] is True
    assert res["authenticode_signed"] is True
    assert res["package_ready_for_review"] is True
    assert res["submission_requires_user_approval"] is True
    assert res["auto_submit_allowed"] is False


def test_windows_store_readiness_detects_missing_fields_and_unverified_wack():
    res = evaluate_windows_store_readiness(
        _valid_msix(publisher=""),
        _valid_listing(privacy_policy_url="http://insecure.example/privacy", screenshots=[]),
        wack_passed=False,
        authenticode_signed=False,
    )
    assert res["msix_ready"] is False
    assert "publisher" in res["missing_msix_fields"]
    assert res["listing_ready"] is False
    assert "screenshots" in res["missing_listing_fields"]
    assert res["privacy_policy_https"] is False
    assert res["package_ready_for_review"] is False
    assert res["submission_requires_user_approval"] is True
