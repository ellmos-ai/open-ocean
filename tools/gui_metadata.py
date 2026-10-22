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
