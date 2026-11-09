# -*- coding: utf-8 -*-
"""Contract tests for PB-16 / PB-20 Product Line Branding ("Ocean" with "BACH" subtitle)."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.ocean_origin import OceanOriginApp
from tools.store_readiness import DEFAULT_APPX_MANIFEST_PATH, DEFAULT_STORE_LISTING_PATH

ROOT = Path(__file__).resolve().parents[1]
BRANDING_MANIFEST_PATH = ROOT / "architecture" / "product-branding.v1.json"


def test_pb16_product_branding_manifest_and_cross_surface_consistency() -> None:
    """Verify README, PWA Origin, and Windows Store manifests align with product-branding.v1.json."""
    assert BRANDING_MANIFEST_PATH.is_file(), "product-branding.v1.json must exist"
    branding = json.loads(BRANDING_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert branding["schema"] == "ellmos.product-branding.v1"
    assert branding["product_name"] == "Ocean"
    assert branding["subtitle"] == "BACH"
    assert branding["store_display_name"] == "Ocean"
    assert "BACH" in branding["store_subtitle"]

    # 1. Windows Store listing metadata (PB-16 / PB-20)
    listing = json.loads(DEFAULT_STORE_LISTING_PATH.read_text(encoding="utf-8"))
    assert listing["display_name"] == branding["store_display_name"]
    assert listing["subtitle"] == branding["store_subtitle"]
    assert branding["subtitle"] in listing["short_description"]

    # 2. Windows Store AppxManifest.xml (PB-16 / PB-20)
    tree = ET.parse(DEFAULT_APPX_MANIFEST_PATH)
    root = tree.getroot()
    ns = {
        "f": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
        "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
    }
    prop_display = root.find("f:Properties/f:DisplayName", ns)
    assert prop_display is not None and prop_display.text == branding["store_display_name"]
    vis_elem = root.find("f:Applications/f:Application/uap:VisualElements", ns)
    assert vis_elem is not None
    assert vis_elem.attrib.get("DisplayName") == branding["store_display_name"]
    assert branding["subtitle"] in vis_elem.attrib.get("Description", "")

    # 3. OceanOriginApp PWA title & short_name
    async def dummy_provider(scope, receive, send):
        return None

    origin_app = OceanOriginApp(dummy_provider)
    assert "OCEAN" in origin_app.title.upper()

    # 4. READMEs reference both Ocean and BACH
    for readme_name in ("README.md", "README_de.md"):
        text = (ROOT / readme_name).read_text(encoding="utf-8")
        assert f"# {branding['repository_slug']}" in text
        assert "BACH" in text or "Bach" in text
