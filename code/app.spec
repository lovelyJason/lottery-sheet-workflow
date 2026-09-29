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
    runtime_hooks=[str(ROOT / "wincompat" / "rthook.py")],
    noarchive=False,
)
PATCHED = ROOT / "wincompat" / "out" / "tree"


def retarget(entry):
    dest = str(entry[0]).replace("\\", "/")
    patched = PATCHED / dest
    if patched.is_file():
        return (entry[0], str(patched), *entry[2:])
    return entry


a.binaries = [retarget(entry) for entry in a.binaries]
if PATCHED.is_dir():
    present = {str(entry[0]).replace("\\", "/").lower() for entry in a.binaries}
    typecode = next((entry[2] for entry in a.binaries if len(entry) > 2), "BINARY")
    sep = "\\" if any("\\" in str(entry[0]) for entry in a.binaries) else "/"
    for path in PATCHED.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".dll":
            continue
        rel = path.relative_to(PATCHED).as_posix()
        if rel.lower() in present:
            continue
        a.binaries.append((rel.replace("/", sep), str(path), typecode))
        present.add(rel.lower())

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
