"""OCEAN-owned runtime entry point around the selected ellmos-core provider."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from ellmos_core.app import app as provider_app
from ellmos_core.config import settings, validate_model_locality, validate_production_security
from ocean_origin import OceanOriginApp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.gui_bridge import GuiBridge, bridge_from_workspace, mount_gui_bridge  # noqa: E402
from ellmos_core.web import require_admin, require_auth  # noqa: E402

workspace = os.environ.get("OCEAN_WORKSPACE")
commit, digest = os.environ.get("OCEAN_GUI_SOURCE_COMMIT"), os.environ.get("OCEAN_GUI_ARCHIVE_SHA256")
bridge = bridge_from_workspace(Path(workspace), gui_pins=(commit, digest) if commit and digest else None) if workspace else GuiBridge()
mount_gui_bridge(provider_app, bridge, require_auth, require_admin)


app = OceanOriginApp(
    provider_app,
    prefix=os.environ.get("ELLMOS_CORE_CONSOLE_PREFIX", "/control"),
    title=os.environ.get("OCEAN_OPERATOR_TITLE", "OCEAN Full Dev"),
    gui=bridge.gui,
)


def main() -> None:
    validate_production_security()
    validate_model_locality()
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False, workers=1)


if __name__ == "__main__":
    main()
