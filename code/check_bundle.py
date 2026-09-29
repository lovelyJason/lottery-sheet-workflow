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
        "pyside6/qtmath.dll",
        "pyside6/qtsynch.dll",
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
    for required_import in ("qtmath.dll", "qtsynch.dll", "kernel32.dll", "user32.dll"):
        if required_import not in qt_core:
            raise SystemExit(f"Qt6Core.dll does not import {required_import}: {qt_core}")
    for forbidden in ("icuuc.dll", "api-ms-win-crt-math-l1-1-0.dll", "qtcore32.dll", "qtuser.dll"):
        if forbidden in qt_core:
            raise SystemExit(f"Qt6Core.dll still imports {forbidden}")

    qt_gui = imports(reader, "PySide6\\Qt6Gui.dll")
    for required_import in ("qtd12.dll", "d3d11.dll", "dxgi.dll", "dwrite.dll", "uxtheme.dll"):
        if required_import not in qt_gui:
            raise SystemExit(f"Qt6Gui.dll does not import {required_import}: {qt_gui}")
    if "d3d12.dll" in qt_gui:
        raise SystemExit("Qt6Gui.dll still imports d3d12.dll")

    windows = imports(reader, "PySide6\\plugins\\platforms\\qwindows.dll")
    for required_import in ("user32.dll", "d3d9.dll", "dwmapi.dll", "qt6gui.dll"):
        if required_import not in windows:
            raise SystemExit(f"qwindows.dll does not import {required_import}: {windows}")
    for forbidden in ("qtuser.dll", "qtcore32.dll", "qtd3d.dll", "qtdwm.dll", "qtdpi.dll"):
        if forbidden in windows:
            raise SystemExit(f"qwindows.dll was redirected to {forbidden}")
    print("bundle checks passed")


if __name__ == "__main__":
    main()
