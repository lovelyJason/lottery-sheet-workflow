"""Load the Qt runtime DLLs shipped inside the exe before QtCore is imported."""

import os
import sys


_DLL_DIRS = []


def _preload() -> None:
    if sys.platform != "win32" or not hasattr(sys, "_MEIPASS"):
        return
    import ctypes

    base = sys._MEIPASS
    pyside = os.path.join(base, "PySide6")
    folders = [
        pyside,
        os.path.join(base, "shiboken6"),
        base,
        os.path.join(pyside, "plugins", "platforms"),
        os.path.join(pyside, "plugins", "styles"),
        os.path.join(pyside, "plugins", "imageformats"),
        os.path.join(pyside, "plugins", "iconengines"),
    ]
    path = os.environ.get("PATH", "")
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        try:
            # Keep the cookie. Dropping it removes the directory again.
            _DLL_DIRS.append(os.add_dll_directory(folder))
        except (AttributeError, OSError):
            pass
        path = folder + os.pathsep + path
    os.environ["PATH"] = path
    os.environ["QT_PLUGIN_PATH"] = os.path.join(pyside, "plugins")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(pyside, "plugins", "platforms")

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
