# -*- mode: python ; coding: utf-8 -*-
"""Windows bundle: ship the complete PySide6 and shiboken6 packages."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
pyside_datas, pyside_binaries, pyside_hidden = collect_all("PySide6")
shiboken_datas, shiboken_binaries, shiboken_hidden = collect_all("shiboken6")

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=pyside_binaries + shiboken_binaries,
    datas=[(str(ROOT / "assets"), "assets"), *pyside_datas, *shiboken_datas, *collect_data_files("tzdata")],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
        "shiboken6",
        "tzdata",
        *pyside_hidden,
        *shiboken_hidden,
        *collect_submodules("tzdata"),
    ],
    noarchive=False,
)

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
