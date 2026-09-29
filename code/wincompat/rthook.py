"""Load the Qt runtime DLLs shipped inside the exe before QtCore is imported."""

import os
import sys


def _preload() -> None:
    if sys.platform != "win32" or not hasattr(sys, "_MEIPASS"):
        return
    import ctypes

    base = sys._MEIPASS
    folders = (
        os.path.join(base, "PySide6"),
        os.path.join(base, "shiboken6"),
        base,
    )
    path = os.environ.get("PATH", "")
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        try:
            os.add_dll_directory(folder)
        except (AttributeError, OSError):
            pass
        path = folder + os.pathsep + path
    os.environ["PATH"] = path

    names = (
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "concrt140.dll",
        "python312.dll",
        "python3.dll",
    )
    for folder in folders:
        for name in names:
            candidate = os.path.join(folder, name)
            if os.path.exists(candidate):
                ctypes.WinDLL(candidate)


_preload()
