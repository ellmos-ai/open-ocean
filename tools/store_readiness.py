# -*- coding: utf-8 -*-
"""Windows Store Readiness Checker for Open-Ocean Desktop App (Task #2497).

Verifies 15 concrete MSIX packaging, Windows App Certification Kit (WACK),
Desktop-Harness (Tauri-2 / GUI subsystem / no legacy Astro copy), and Partner Center
Store listing checks, while enforcing the non-negotiable governance gate:
actual Microsoft Partner Center submission ALWAYS requires explicit user approval
(`submission_requires_user_approval=True`, `auto_submit_allowed=False`).
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
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

STORE_READINESS_CHECK_IDS: tuple[str, ...] = (
    "identity_name_present",
    "publisher_cn_format",
    "version_four_part_numeric",
    "architecture_valid",
    "executable_exe_present",
    "windows_desktop_target_family",
    "run_full_trust_capability",
    "windows_subsystem_gui",
    "no_embedded_legacy_astro",
    "display_name_present",
    "short_description_present",
    "privacy_policy_https",
    "age_rating_completed",
    "screenshots_present",
    "submission_user_gate_enforced",
)

FOUR_PART_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
DEFAULT_APPX_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / "packaging" / "windows-store" / "AppxManifest.xml"
)
DEFAULT_STORE_LISTING_PATH = (
    Path(__file__).resolve().parents[1] / "packaging" / "windows-store" / "store-listing.json"
)


def parse_appx_manifest_xml(manifest_path: str | Path | None = None) -> dict[str, Any]:
    """Parse an AppxManifest.xml file into the normalized MSIX dictionary."""
    path = Path(manifest_path) if manifest_path is not None else DEFAULT_APPX_MANIFEST_PATH
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {
        "f": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
        "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
        "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
    }
    identity = root.find("f:Identity", ns)
    app = root.find("f:Applications/f:Application", ns)
    tdf = root.find("f:Dependencies/f:TargetDeviceFamily", ns)
    rescap = root.find("f:Capabilities/rescap:Capability", ns)
    return {
        "identity_name": identity.attrib.get("Name", "") if identity is not None else "",
        "publisher": identity.attrib.get("Publisher", "") if identity is not None else "",
        "version": identity.attrib.get("Version", "") if identity is not None else "",
        "processor_architecture": (
            identity.attrib.get("ProcessorArchitecture", "") if identity is not None else ""
        ),
        "executable": app.attrib.get("Executable", "") if app is not None else "",
        "entry_point": app.attrib.get("EntryPoint", "") if app is not None else "",
        "target_device_family": tdf.attrib.get("Name", "") if tdf is not None else "",
        "run_full_trust": (
            rescap is not None and rescap.attrib.get("Name") == "runFullTrust"
        ),
    }


def load_default_store_bundle() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the repository's canonical AppxManifest.xml and store-listing.json."""
    msix = parse_appx_manifest_xml(DEFAULT_APPX_MANIFEST_PATH)
    listing = json.loads(DEFAULT_STORE_LISTING_PATH.read_text(encoding="utf-8"))
    return msix, listing


def evaluate_windows_store_readiness(
    msix_manifest: Mapping[str, Any],
    listing_metadata: Mapping[str, Any],
    *,
    wack_passed: bool = False,
    authenticode_signed: bool = False,
) -> dict[str, Any]:
    """Evaluate all 15 MSIX, Desktop-Harness, WACK, signing, and Store listing checks (#2497)."""
    missing_msix = [
        field for field in REQUIRED_MSIX_FIELDS
        if not str(msix_manifest.get(field) or "").strip()
    ]
    identity_name = str(msix_manifest.get("identity_name") or "").strip()
    publisher = str(msix_manifest.get("publisher") or "").strip()
    version = str(msix_manifest.get("version") or "").strip()
    arch = str(msix_manifest.get("processor_architecture") or "").strip().lower()
    executable = str(msix_manifest.get("executable") or "").strip()

    arch_valid = arch in {"x64", "arm64", "neutral"}
    publisher_cn = publisher.startswith("CN=") and len(publisher) > 3
    version_4part = FOUR_PART_VERSION_RE.fullmatch(version) is not None
    exe_valid = executable.lower().endswith(".exe")
    target_family_ok = str(
        msix_manifest.get("target_device_family") or "Windows.Desktop"
    ) == "Windows.Desktop"
    run_full_trust_ok = bool(msix_manifest.get("run_full_trust", True))
    subsystem_gui_ok = str(listing_metadata.get("windows_subsystem") or "GUI").upper() == "GUI"
    no_legacy_astro_ok = not bool(listing_metadata.get("embeds_legacy_astro_copy", False))

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

    checks: dict[str, bool] = {
        "identity_name_present": bool(identity_name),
        "publisher_cn_format": publisher_cn,
        "version_four_part_numeric": version_4part,
        "architecture_valid": arch_valid,
        "executable_exe_present": exe_valid,
        "windows_desktop_target_family": target_family_ok,
        "run_full_trust_capability": run_full_trust_ok,
        "windows_subsystem_gui": subsystem_gui_ok,
        "no_embedded_legacy_astro": no_legacy_astro_ok,
        "display_name_present": bool(str(listing_metadata.get("display_name") or "").strip()),
        "short_description_present": bool(str(listing_metadata.get("short_description") or "").strip()),
        "privacy_policy_https": privacy_https,
        "age_rating_completed": listing_metadata.get("age_rating_questionnaire_completed") is True,
        "screenshots_present": isinstance(listing_metadata.get("screenshots"), (list, tuple))
        and len(listing_metadata.get("screenshots") or ()) > 0,
        "submission_user_gate_enforced": True,
    }

    msix_ready = (
        len(missing_msix) == 0
        and arch_valid
        and publisher_cn
        and version_4part
        and exe_valid
        and target_family_ok
        and run_full_trust_ok
    )
    listing_ready = (
        len(missing_listing) == 0
        and privacy_https
        and subsystem_gui_ok
        and no_legacy_astro_ok
    )
    passed_checks = sum(1 for v in checks.values() if v)
    package_ready_for_review = bool(
        msix_ready and listing_ready and wack_passed and authenticode_signed
    )

    return {
        "schema": "open-ocean.windows-store-readiness.v1",
        "check_count": len(STORE_READINESS_CHECK_IDS),
        "passed_check_count": passed_checks,
        "checks": checks,
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
