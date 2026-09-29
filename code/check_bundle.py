"""Fail the Windows build if the exe cannot load QtCore on a machine without ICU."""

import pefile
from PyInstaller.archive.readers import CArchiveReader

EXE = "dist/黄金万两.exe"


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
    )
    missing = [token for token in required if token not in names]
    if missing:
        raise SystemExit("missing from exe: " + ", ".join(missing))
    if any("webengine" in name for name in names):
        raise SystemExit("webengine was packed")

    qt_core = pefile.PE(data=reader.extract("PySide6\\Qt6Core.dll"))
    imports = [entry.dll.decode().lower() for entry in qt_core.DIRECTORY_ENTRY_IMPORT]
    if "icuuc.dll" in imports:
        raise SystemExit("Qt6Core.dll imports icuuc.dll, which the PySide6 wheel does not ship")
    print("Qt6Core imports:", ", ".join(imports))


if __name__ == "__main__":
    main()
