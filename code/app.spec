# -*- mode: python ; coding: utf-8 -*-
"""Windows bundle: keep Qt Widgets, drop WebEngine and the other unused Qt libraries."""

import os
from pathlib import Path

import PySide6
import shiboken6
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)

# Substrings matched against the packaged path. Do not use a bare "3d":
# that would also drop d3dcompiler, which Qt6Gui needs.
HEAVY = (
    "webengine",
    "webchannel",
    "websockets",
    "webview",
    "multimedia",
    "qt6quick",
    "qt6qml",
    "/qml/",
    "qt63d",
    "qt6pdf",
    "qt6bluetooth",
    "qt6positioning",
    "qt6sensors",
    "qt6serial",
    "qt6charts",
    "qt6datavis",
    "virtualkeyboard",
    "texttospeech",
    "remoteobjects",
    "qt6scxml",
    "spatialaudio",
    "qt6designer",
    "qt6graphs",
    "qt6location",
    "qt6nfc",
    "qt6sql",
    "qt6test",
    "qt6help",
    "uitools",
    "openglwidgets",
    "qt6concurrent",
    "translations/",
)


def heavy(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    name = lowered.rsplit("/", 1)[-1]
    if name.startswith("api-ms-win-"):
        return True
    return any(token in lowered for token in HEAVY)


def qt_dlls() -> list[tuple[str, str]]:
    found = []
    for package_file in (PySide6.__file__, shiboken6.__file__):
        package = Path(package_file).resolve().parent
        anchor = package.parent
        for dirpath, _, filenames in os.walk(package):
            for filename in filenames:
                if not filename.lower().endswith(".dll"):
                    continue
                source = str(Path(dirpath) / filename)
                if heavy(source):
                    continue
                dest = Path(dirpath).resolve().relative_to(anchor)
                found.append((source, str(dest)))
    runtime = (
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "concrt140.dll",
        "python3.dll",
        "python312.dll",
        "qtcore32.dll",
        "qtuser.dll",
        "qtmath.dll",
        "qtsynch.dll",
    )
    pyside = Path(PySide6.__file__).resolve().parent
    for name in runtime:
        source = pyside / name
        if source.exists():
            found.append((str(source), "."))
    return found


a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=qt_dlls(),
    datas=[(str(ROOT / "assets"), "assets"), *collect_data_files("tzdata")],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
        "shiboken6",
        "tzdata",
        *collect_submodules("tzdata"),
    ],
    runtime_hooks=[str(ROOT / "wincompat" / "rthook.py")],
    noarchive=False,
)
a.binaries = [entry for entry in a.binaries if not heavy(entry[0])]
a.datas = [entry for entry in a.datas if not heavy(entry[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="黄金万两",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "assets" / "app-icon.ico"),
)
