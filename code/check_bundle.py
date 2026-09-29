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
    qt_core = imports(reader, "PySide6\\Qt6Core.dll")
    for forbidden in ("qtmath.dll", "qtsynch.dll", "qtd12.dll", "qtcore32.dll", "qtuser.dll", "icuuc.dll"):
        if forbidden in qt_core:
            raise SystemExit(f"Qt6Core.dll imports {forbidden}")
    if "kernel32.dll" not in qt_core:
        raise SystemExit("Qt6Core.dll does not import kernel32.dll")
    qt_gui = imports(reader, "PySide6\\Qt6Gui.dll")
    for required_import in ("d3d11.dll", "d3d12.dll"):
        if required_import not in qt_gui:
            raise SystemExit(f"Qt6Gui.dll does not import {required_import}")
    print("full PySide6 bundle ok", sum(name.endswith(".dll") for name in names), "dlls")


if __name__ == "__main__":
    main()
