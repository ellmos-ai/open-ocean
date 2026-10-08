# SPDX-License-Identifier: MIT
"""Compatibility imports for the native Ocean GUI consumer; no second verifier."""
try:
    from .gui_consumer import (  # noqa: F401
        MANIFEST, RECEIPT, INSTALLED_ARCHIVE, MAX_BYTES, MAX_FILES,
        GuiReleaseError, VerifiedGuiRelease, verify_gui_archive, verify_installed_gui,
    )
except ImportError:  # direct ocean-dev entry point
    from gui_consumer import (  # noqa: F401
        MANIFEST, RECEIPT, INSTALLED_ARCHIVE, MAX_BYTES, MAX_FILES,
        GuiReleaseError, VerifiedGuiRelease, verify_gui_archive, verify_installed_gui,
    )
