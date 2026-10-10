"""Open ordinary web links reliably from the packaged desktop application."""
from __future__ import annotations

import os
import sys
import webbrowser
from urllib.parse import urlsplit

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_external_url(url: str) -> bool:
    """Open an HTTP(S) URL, preferring the native Windows shell."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("只能打开 http:// 或 https:// 网址")
    if sys.platform == "win32":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except (AttributeError, OSError):
            pass
    try:
        if QDesktopServices.openUrl(QUrl(url)):
            return True
    except (OSError, RuntimeError):
        pass
    try:
        return bool(webbrowser.open(url, new=2, autoraise=True))
    except (OSError, webbrowser.Error):
        return False
