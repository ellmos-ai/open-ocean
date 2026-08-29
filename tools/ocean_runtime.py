"""OCEAN-owned runtime entry point around the selected ellmos-core provider."""

from __future__ import annotations

import os

import uvicorn

from ellmos_core.app import app as provider_app
from ellmos_core.config import settings, validate_model_locality, validate_production_security
from ocean_origin import OceanOriginApp


app = OceanOriginApp(
    provider_app,
    prefix=os.environ.get("ELLMOS_CORE_CONSOLE_PREFIX", "/control"),
    title=os.environ.get("OCEAN_OPERATOR_TITLE", "OCEAN Full Dev"),
)


def main() -> None:
    validate_production_security()
    validate_model_locality()
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False, workers=1)


if __name__ == "__main__":
    main()
