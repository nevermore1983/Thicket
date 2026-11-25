"""Windows' own "Country or region" setting, for the welcome's suggestion
(docs/27-find-your-region-plan.md, section 4). Read on this computer, never sent anywhere.
"""

from __future__ import annotations

import sys


def windows_country() -> str | None:
    """The country set in Windows (Settings › Time & language › Language & region) as its
    two-letter code ('GB', 'KE'); None when it isn't a country (Windows can say 'World')
    or can't be read, and away from Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        answer = ctypes.create_unicode_buffer(16)
        if not ctypes.windll.kernel32.GetUserDefaultGeoName(answer, len(answer)):
            return None
    except (AttributeError, OSError):  # older Windows without it
        return None
    code = answer.value.strip().upper()
    return code if len(code) == 2 and code.isalpha() else None
