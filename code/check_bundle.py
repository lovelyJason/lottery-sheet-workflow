"""Fail the Windows build when Qt still depends on a DLL the VPS may not have."""

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
        "pyside6/qtcore32.dll",
        "pyside6/qtmath.dll",
        "pyside6/qtsynch.dll",
        "pyside6/qtuser.dll",
        "pyside6/qtd3d.dll",
        "pyside6/qtd12.dll",
        "pyside6/vcruntime140_1.dll",
        "pyside6/msvcp140.dll",
        "pyside6/msvcp140_1.dll",
        "shiboken6/shiboken6.abi3.dll",
        "pyside6/plugins/platforms/qwindows.dll",
        "python3.dll",
        "tzdata/zoneinfo/asia/shanghai",
    )
    missing = [token for token in required if token not in names]
    if missing:
        raise SystemExit("missing from exe: " + ", ".join(missing))
    if any("webengine" in name for name in names):
        raise SystemExit("webengine was packed")
    banned = [name for name in names if name.rsplit("/", 1)[-1].startswith("api-ms-win-")]
    if banned:
        raise SystemExit("api-ms dlls were packed: " + ", ".join(banned[:8]))

    qt_core = imports(reader, "PySide6\\Qt6Core.dll")
    for required_import in ("qtcore32.dll", "qtmath.dll", "qtsynch.dll", "qtuser.dll"):
        if required_import not in qt_core:
            raise SystemExit(f"Qt6Core.dll does not import {required_import}: {qt_core}")
    for forbidden in ("kernel32.dll", "icuuc.dll", "api-ms-win-crt-math-l1-1-0.dll"):
        if forbidden in qt_core:
            raise SystemExit(f"Qt6Core.dll still imports {forbidden}")

    qt_gui = imports(reader, "PySide6\\Qt6Gui.dll")
    for required_import in ("qtd3d.dll", "qtd12.dll", "qtdx.dll", "qtdwr.dll", "qtuxt.dll"):
        if required_import not in qt_gui:
            raise SystemExit(f"Qt6Gui.dll does not import {required_import}: {qt_gui}")
    for forbidden in ("d3d11.dll", "d3d12.dll", "dxgi.dll", "dwrite.dll", "uxtheme.dll"):
        if forbidden in qt_gui:
            raise SystemExit(f"Qt6Gui.dll still imports {forbidden}")

    widgets = imports(reader, "PySide6\\Qt6Widgets.dll")
    for required_import in ("qtdwm.dll", "qtuxt.dll"):
        if required_import not in widgets:
            raise SystemExit(f"Qt6Widgets.dll does not import {required_import}: {widgets}")
    windows = imports(reader, "PySide6\\plugins\\platforms\\qwindows.dll")
    for required_import in ("qtdwm.dll", "qtd9.dll", "qtdpi.dll", "qtuser.dll", "qtcore32.dll", "qtmath.dll"):
        if required_import not in windows:
            raise SystemExit(f"qwindows.dll does not import {required_import}: {windows}")
    print("bundle checks passed")


if __name__ == "__main__":
    main()
