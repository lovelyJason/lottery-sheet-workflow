"""Fail the Windows build if PySide6 was trimmed or QtCore was retargeted."""

import pefile
from PyInstaller.archive.readers import CArchiveReader

EXE = "dist/黄金万两.exe"


def imports(reader: CArchiveReader, name: str) -> list[str]:
    pe = pefile.PE(data=reader.extract(name))
    return [entry.dll.decode().lower() for entry in pe.DIRECTORY_ENTRY_IMPORT]


def main() -> None:
    reader = CArchiveReader(EXE)
    names = [name.replace("\\", "/").lower() for name in reader.toc]
    required = (
        "pyside6/qt6core.dll",
        "pyside6/qt6gui.dll",
        "pyside6/qt6widgets.dll",
        "pyside6/qtcore.pyd",
        "pyside6/vcruntime140_1.dll",
        "pyside6/msvcp140.dll",
        "shiboken6/shiboken6.abi3.dll",
        "pyside6/plugins/platforms/qwindows.dll",
        "python3.dll",
        "tzdata/zoneinfo/asia/shanghai",
    )
    missing = [token for token in required if token not in names]
    if missing:
        raise SystemExit("missing from exe: " + ", ".join(missing))
    if not any("webengine" in name and name.endswith(".dll") for name in names):
        raise SystemExit("PySide6 WebEngine was not packed")
    for token in (
        "pyside6/qtcore32.dll",
        "pyside6/qtcorestub.dll",
        "pyside6/qtmath.dll",
        "pyside6/qtmathimpl.dll",
        "pyside6/qtsynch.dll",
        "pyside6/qtd12.dll",
        "pyside6/qtuser.dll",
        "pyside6/plugins/platforms/qtuser.dll",
        "pyside6/ucrtbase.dll",
        "pyside6/api-ms-win-crt-runtime-l1-1-0.dll",
        "ucrtbase.dll",
    ):
        if token not in names:
            raise SystemExit("missing shim " + token)
    qt_core = imports(reader, "PySide6\\Qt6Core.dll")
    for required_import in ("qtcore32.dll", "qtmath.dll", "qtsynch.dll"):
        if required_import not in qt_core:
            raise SystemExit(f"Qt6Core.dll does not import {required_import}: {qt_core}")
    for forbidden in ("kernel32.dll", "icuuc.dll", "api-ms-win-crt-math-l1-1-0.dll"):
        if forbidden in qt_core:
            raise SystemExit(f"Qt6Core.dll still imports {forbidden}")
    qt_gui = imports(reader, "PySide6\\Qt6Gui.dll")
    for required_import in ("d3d11.dll", "qtd12.dll", "qtuser.dll"):
        if required_import not in qt_gui:
            raise SystemExit(f"Qt6Gui.dll does not import {required_import}: {qt_gui}")
    if "d3d12.dll" in qt_gui:
        raise SystemExit("Qt6Gui.dll still imports d3d12.dll")
    windows = imports(reader, "PySide6\\plugins\\platforms\\qwindows.dll")
    if "qtuser.dll" not in windows or "user32.dll" in windows:
        raise SystemExit(f"qwindows user32 redirect is wrong: {windows}")
    if "d3d9.dll" not in windows or "dwmapi.dll" not in windows:
        raise SystemExit("qwindows lost its system graphics libraries")
    print("full PySide6 bundle ok", sum(name.endswith(".dll") for name in names), "dlls")


if __name__ == "__main__":
    main()
