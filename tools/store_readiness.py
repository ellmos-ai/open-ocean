# -*- coding: utf-8 -*-
"""Windows Store Readiness Checker for Open-Ocean Desktop App (Task #2497).

Verifies MSIX packaging metadata, Windows App Certification Kit (WACK) preflight
requirements, Store listing completeness (privacy policy, age rating, assets),
and enforces the non-negotiable governance gate: actual Microsoft Partner Center
submission ALWAYS requires explicit user approval (submission_requires_user_approval=True).
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

REQUIRED_MSIX_FIELDS = (
    "identity_name",
    "publisher",
    "version",
    "processor_architecture",
    "executable",
)

REQUIRED_LISTING_FIELDS = (
    "display_name",
    "short_description",
    "privacy_policy_url",
    "age_rating_questionnaire_completed",
    "screenshots",
)


def evaluate_windows_store_readiness(
    msix_manifest: Mapping[str, Any],
    listing_metadata: Mapping[str, Any],
    *,
    wack_passed: bool = False,
    authenticode_signed: bool = False,
) -> dict[str, Any]:
    """Evaluate MSIX, WACK, signing, and Store listing readiness (#2497)."""
    missing_msix = [
        field for field in REQUIRED_MSIX_FIELDS
        if not str(msix_manifest.get(field) or "").strip()
    ]
    arch = str(msix_manifest.get("processor_architecture") or "").strip().lower()
    arch_valid = arch in {"x64", "arm64", "neutral"}

    missing_listing = []
    for field in REQUIRED_LISTING_FIELDS:
        val = listing_metadata.get(field)
        if field == "age_rating_questionnaire_completed":
            if val is not True:
                missing_listing.append(field)
        elif field == "screenshots":
            if not isinstance(val, (list, tuple)) or len(val) == 0:
                missing_listing.append(field)
        else:
            if not str(val or "").strip():
                missing_listing.append(field)

    privacy_url = str(listing_metadata.get("privacy_policy_url") or "").strip()
    privacy_https = privacy_url.startswith("https://")

    msix_ready = len(missing_msix) == 0 and arch_valid
    listing_ready = len(missing_listing) == 0 and privacy_https
    package_ready_for_review = bool(
        msix_ready and listing_ready and wack_passed and authenticode_signed
    )

    return {
        "schema": "open-ocean.windows-store-readiness.v1",
        "msix_ready": msix_ready,
        "missing_msix_fields": missing_msix,
        "architecture_valid": arch_valid,
        "wack_passed": bool(wack_passed),
        "authenticode_signed": bool(authenticode_signed),
        "listing_ready": listing_ready,
        "missing_listing_fields": missing_listing,
        "privacy_policy_https": privacy_https,
        "package_ready_for_review": package_ready_for_review,
        "submission_requires_user_approval": True,
        "auto_submit_allowed": False,
    }
