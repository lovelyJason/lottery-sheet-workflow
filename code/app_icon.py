"""Put the bundled picture on the window, the macOS Dock, and the Windows taskbar."""

from __future__ import annotations

import ctypes
import ctypes.util
import struct
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent / "assets"
ICON_JPG = ASSETS / "app-icon.jpg"
ICON_PNG = ASSETS / "app-icon.png"
ICON_ICO = ASSETS / "app-icon.ico"
WINDOWS_APP_ID = "LotterySheetWorkflow.Desktop"


def set_windows_app_user_model_id(app_id: str = WINDOWS_APP_ID) -> None:
    """Call before QApplication. Otherwise the taskbar keeps python.exe's icon."""
    if sys.platform != "win32":
        return
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def build_qicon() -> QIcon:
    icon = QIcon()
    for path in (ICON_ICO, ICON_PNG):
        if path.is_file():
            icon.addFile(str(path))
    return icon


def apply_app_icon(app: QApplication) -> QIcon:
    icon = build_qicon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    _set_macos_dock_icon(_dock_image_path())
    return icon


def _dock_image_path() -> Path | None:
    for path in (ICON_PNG, ICON_JPG):
        if path.is_file():
            return path
    return None


def _set_macos_dock_icon(path: Path | None) -> None:
    if sys.platform != "darwin" or path is None:
        return
    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    lib.objc_getClass.restype = ctypes.c_void_p
    lib.objc_getClass.argtypes = [ctypes.c_char_p]
    lib.sel_registerName.restype = ctypes.c_void_p
    lib.sel_registerName.argtypes = [ctypes.c_char_p]

    def send(restype, argtypes):
        return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(
            ("objc_msgSend", lib)
        )

    def sel(name: bytes) -> ctypes.c_void_p:
        return lib.sel_registerName(name)

    ns_app = send(ctypes.c_void_p, [])(lib.objc_getClass(b"NSApplication"), sel(b"sharedApplication"))
    ns_path = send(ctypes.c_void_p, [ctypes.c_char_p])(
        lib.objc_getClass(b"NSString"),
        sel(b"stringWithUTF8String:"),
        str(path).encode(),
    )
    image = send(ctypes.c_void_p, [])(lib.objc_getClass(b"NSImage"), sel(b"alloc"))
    image = send(ctypes.c_void_p, [ctypes.c_void_p])(image, sel(b"initWithContentsOfFile:"), ns_path)
    if not image:
        return
    send(None, [ctypes.c_void_p])(ns_app, sel(b"setApplicationIconImage:"), image)


def write_ico(pngs: list[tuple[int, bytes]], dest: Path) -> None:
    """Vista-style ICO that stores PNG frames. Windows taskbar accepts this."""
    count = len(pngs)
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    images = b""
    offset = 6 + 16 * count
    for size, data in pngs:
        box = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", box, box, 0, 0, 1, 32, len(data), offset)
        images += data
        offset += len(data)
    dest.write_bytes(header + entries + images)
