# SPDX-License-Identifier: MIT
"""Shared, non-secret GUI metadata for both Ocean consumer entry points.

Serving metadata is not proof of a native task backend, its storage, or its
authority. Until that binding has a verified observer, report it as unknown.
"""
from __future__ import annotations

from datetime import datetime, timezone

BRAND_SCHEMA = "ellmos-system-gui.brand.v1"
ORIGIN_SCHEMA = "ellmos-system-gui.backend-origin.v1"
DEFAULT_BRAND = {
    "schema": BRAND_SCHEMA, "label": "Ocean", "product": "Open Ocean",
    "logo_text": "OCEAN", "logo_path": None, "theme": "ocean",
    "entry_point": "open-ocean", "edition": "ocean",
    "subtitle": None, "foreground_product": "Open Ocean",
}
BACH_ON_OCEAN_BRAND = {
    "schema": BRAND_SCHEMA, "label": "Ocean · BACH", "product": "Open Ocean",
    "logo_text": "OCEAN · BACH", "logo_path": None, "theme": "ocean-bach",
    "entry_point": "bach", "edition": "bach",
    "subtitle": "BACH — a curated edition of Ocean",
    "foreground_product": "Open Ocean",
}


ONBOARDING_WIZARD_SCHEMA = "ellmos-system-gui.onboarding-wizard.v1"
ONBOARDING_PRIORITY_STAGES = (
    {
        "priority": 1,
        "stage_id": "models_and_subscriptions",
        "title_de": "1. Modelle, Subscriptions & API-Zugänge",
        "title_en": "1. Models, Subscriptions & API Keys",
        "items": (
            "ollama_local",
            "anthropic_claude",
            "openai_codex",
            "google_gemini",
            "openrouter",
            "ollama_cloud",
            "kimi_moonshot",
        ),
    },
    {
        "priority": 2,
        "stage_id": "system_mcps_and_authority",
        "title_de": "2. Wichtige System-MCPs, Berechtigungs- & Autoritätseinstellungen",
        "title_en": "2. Core System MCPs, Permissions & Authority Settings",
        "items": (
            "ellmos-filecommander",
            "ellmos-controlcenter-mcp",
            "ellmos-codecommander",
            "ellmos-homebase-mcp",
            "write_scope",
            "completion_and_review_mode",
            "escalation_ladder",
        ),
    },
    {
        "priority": 3,
        "stage_id": "connectors",
        "title_de": "3. Connectoren & Kommunikationskanäle (Telegram, WhatsApp, Discord, E-Mail)",
        "title_en": "3. Connectors & Messaging Channels (Telegram, WhatsApp, Discord, Email)",
        "items": ("telegram", "whatsapp", "discord", "email_bridge"),
    },
    {
        "priority": 4,
        "stage_id": "extensions_plugins_mcps_skills",
        "title_de": "4. Ausdehnung (Rinnsal ↔ BACH ↔ Meer), Plugins, weitere MCPs & Skills",
        "title_en": "4. Extent (Rinnsal ↔ BACH ↔ Meer), Plugins, Additional MCPs & Skills",
        "items": ("extent_profile", "plugins", "additional_mcps", "skills", "domain_bundles"),
    },
)


def resolve_entry_point_brand(entry_point: str = "open-ocean") -> dict:
    """Resolve GUI brand contract based on user installation/entry point.

    - 'open-ocean' (or 'ocean'): Pure Ocean branding without BACH branding.
    - 'bach': BACH branding where Ocean stands in the foreground of the GUI
      and BACH is presented as a curated version/form of Ocean.
    """
    normalized = (entry_point or "open-ocean").strip().lower()
    if normalized in ("bach", "ellmos-ai/bach", "bach-edition"):
        return dict(BACH_ON_OCEAN_BRAND)
    return dict(DEFAULT_BRAND)


def build_onboarding_wizard_contract(entry_point: str = "open-ocean") -> dict:
    """Return the Hermes-inspired 4-stage onboarding wizard contract for Installer & System GUI."""
    return {
        "schema": ONBOARDING_WIZARD_SCHEMA,
        "brand": resolve_entry_point_brand(entry_point),
        "reconfigurable_anytime": True,
        "stages": [dict(stage, items=list(stage["items"])) for stage in ONBOARDING_PRIORITY_STAGES],
    }


def unverified_backend_origin() -> dict:
    """Return the common GUI contract without inferring authority from a URL."""
    return {
        "schema": ORIGIN_SCHEMA,
        "mode": "unknown",
        "declared_mode": None,
        "backend_kind": None,
        "instance_label": None,
        "connection_verified": False,
        "schema_verified": False,
        "instance_verified": False,
        "adapter_binding_verified": False,
        "has_claim_authority": False,
        "cache_active": False,
        "source": "not_verified",
        "reason_code": "ocean_backend_adapter_unbound",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
