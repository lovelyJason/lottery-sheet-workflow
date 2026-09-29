"""Retarget Qt's Windows imports so an older VPS can still load QtCore.

Qt 6.9 imports functions that Windows 8.1 and some Windows Server images do not
have. Loading those DLLs then fails with "找不到指定的程序". The shims below keep
the real function when it exists and otherwise return a safe failure.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parent
BUILD = ROOT.parent / "build" / "wincompat"

KERNEL_STUBS = {
    "SetThreadDescription": "Stub_SetThreadDescription",
    "SetThreadInformation": "Stub_SetThreadInformation",
    "GetCurrentPackageFullName": "Stub_GetCurrentPackageFullName",
}
USER_STUBS = {
    "SetCoalescableTimer": "Stub_SetCoalescableTimer",
    "GetSystemMetricsForDpi": "Stub_GetSystemMetricsForDpi",
    "SystemParametersInfoForDpi": "Stub_SystemParametersInfoForDpi",
    "GetDpiForWindow": "Stub_GetDpiForWindow",
    "AdjustWindowRectExForDpi": "Stub_AdjustWindowRectExForDpi",
}
MATH_LOCAL = {"_dclass", "_fdclass"}
SYNCH_EXPORTS = ("WaitOnAddress", "WakeByAddressSingle", "WakeByAddressAll")

# Replacement DLL names must fit in the original import string.
REPLACEMENTS = {
    "kernel32.dll": "qtcore32.dll",
    "user32.dll": "qtuser.dll",
    "api-ms-win-crt-math-l1-1-0.dll": "qtmath.dll",
    "api-ms-win-core-synch-l1-2-0.dll": "qtsynch.dll",
    "d3d11.dll": "qtd3d.dll",
    "d3d12.dll": "qtd12.dll",
    "dxgi.dll": "qtdx.dll",
    "d3d9.dll": "qtd9.dll",
    "dwmapi.dll": "qtdwm.dll",
    "dwrite.dll": "qtdwr.dll",
    "uxtheme.dll": "qtuxt.dll",
    "api-ms-win-shcore-scaling-l1-1-1.dll": "qtdpi.dll",
    "api-ms-win-core-winrt-l1-1-0.dll": "qtwinrt.dll",
    "api-ms-win-core-winrt-string-l1-1-0.dll": "qtwstr.dll",
    "uiautomationcore.dll": "qtui.dll",
}
GRAPHICS = {
    "d3d11.dll",
    "d3d12.dll",
    "dxgi.dll",
    "d3d9.dll",
    "dwmapi.dll",
    "dwrite.dll",
    "uxtheme.dll",
    "api-ms-win-shcore-scaling-l1-1-1.dll",
    "api-ms-win-core-winrt-l1-1-0.dll",
    "api-ms-win-core-winrt-string-l1-1-0.dll",
    "uiautomationcore.dll",
}
ZERO_RETURN = {
    "Direct3DCreate9",
    "OpenThemeData",
    "DwmDefWindowProc",
    "IsAppThemed",
    "IsThemeActive",
    "IsThemeBackgroundPartiallyTransparent",
    "UiaClientsAreListening",
    "UiaHostProviderFromHwnd",
    "UiaReturnRawElementProvider",
}
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


def heavy(path: Path) -> bool:
    text = str(path).replace("\\", "/").lower()
    return any(token in text for token in HEAVY)


def packages() -> list[Path]:
    import PySide6
    import shiboken6

    return [
        Path(PySide6.__file__).resolve().parent,
        Path(shiboken6.__file__).resolve().parent,
    ]


def pe_files() -> list[Path]:
    found = []
    for package in packages():
        for path in package.rglob("*"):
            if path.suffix.lower() not in {".dll", ".pyd"}:
                continue
            if path.name.lower() in set(REPLACEMENTS.values()):
                continue
            if heavy(path):
                continue
            found.append(path)
    return found


def imports_of(path: Path) -> dict[str, list[tuple[str | int, int]]]:
    pe = pefile.PE(data=path.read_bytes(), fast_load=True)
    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        found: dict[str, list[tuple[str | int, int]]] = {}
        if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            return found
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode().lower()
            symbols = []
            for item in entry.imports:
                if item.name:
                    symbols.append((item.name.decode(), 0))
                else:
                    symbols.append((int(item.ordinal), int(item.ordinal)))
            found[dll] = symbols
        return found
    finally:
        pe.close()


def collect_symbols(files: list[Path]) -> dict[str, set]:
    collected = {name: set() for name in REPLACEMENTS}
    for path in files:
        for dll, symbols in imports_of(path).items():
            if dll not in collected:
                continue
            for name, ordinal in symbols:
                collected[dll].add(ordinal or name)
    return collected


def write_def(path: Path, library: str, lines: list[str]) -> None:
    path.write_text(
        "LIBRARY " + library + "\nEXPORTS\n" + "\n".join(f"    {line}" for line in lines) + "\n",
        encoding="ascii",
    )


def emit_thunks(stem: str, modules: list[tuple[str, set]], stubs: dict[str, str]) -> list[str]:
    """Build asm jumps for symbols the system DLL may not export."""
    names = []
    for _dll, symbols in modules:
        for symbol in symbols:
            if isinstance(symbol, str) and symbol not in stubs and symbol not in MATH_LOCAL:
                names.append(symbol)
    names = sorted(set(names))
    asm = ["OPTION CASEMAP:NONE", "EXTERN ensure_loaded:PROC"]
    for name in names:
        asm.append(f"EXTERN real_{name}:QWORD")
    asm.append(".code")
    for name in names:
        asm.extend([
            f"{name} PROC",
            "    push rcx",
            "    push rdx",
            "    push r8",
            "    push r9",
            "    sub rsp, 28h",
            "    call ensure_loaded",
            "    add rsp, 28h",
            "    pop r9",
            "    pop r8",
            "    pop rdx",
            "    pop rcx",
            f"    mov rax, QWORD PTR [real_{name}]",
            "    test rax, rax",
            "    jz fail_" + name,
            "    jmp rax",
            f"fail_{name}:",
            "    xor eax, eax",
            "    ret",
            f"{name} ENDP",
        ])
    asm.append("END")
    (BUILD / f"{stem}.asm").write_text("\n".join(asm) + "\n", encoding="ascii")

    c_lines = ["#define WIN32_LEAN_AND_MEAN", "#include <windows.h>", ""]
    for name in names:
        c_lines.append(f"FARPROC real_{name};")
    c_lines.extend(["", "static volatile LONG load_state;", "", "static void load_all(void) {"])
    for dll, symbols in modules:
        exported = [item for item in symbols if isinstance(item, str) and item not in stubs and item not in MATH_LOCAL]
        if not exported:
            continue
        c_lines.append(f'    HMODULE module = LoadLibraryW(L"{dll}");')
        for name in sorted(set(exported)):
            c_lines.append(f'    real_{name} = module ? GetProcAddress(module, "{name}") : NULL;')
    c_lines.extend([
        "}",
        "",
        "void ensure_loaded(void) {",
        "    LONG previous = InterlockedCompareExchange(&load_state, 2, 0);",
        "    if (previous == 1 || previous == 2) return;",
        "    load_all();",
        "    InterlockedExchange(&load_state, 1);",
        "}",
        "",
    ])
    (BUILD / f"{stem}_load.c").write_text("\n".join(c_lines), encoding="ascii")
    exports = list(names)
    for name, target in sorted(stubs.items()):
        if any(name in symbols for _dll, symbols in modules):
            exports.append(f"{name}={target}")
    for name in sorted(MATH_LOCAL):
        if any(name in symbols for _dll, symbols in modules):
            exports.append(name)
    return exports


def graphics_sources(symbols_by_dll: dict[str, set]) -> None:
    names = []
    ordinals = []
    owners = {}
    for dll, symbols in symbols_by_dll.items():
        if dll not in GRAPHICS:
            continue
        for symbol in symbols:
            previous = owners.get(symbol)
            if previous is not None and previous != dll:
                raise SystemExit(f"{symbol} is imported from both {previous} and {dll}")
            owners[symbol] = dll
            if isinstance(symbol, int):
                ordinals.append(symbol)
            else:
                names.append(symbol)
    names = sorted(set(names))
    ordinals = sorted(set(ordinals))
    asm = ["OPTION CASEMAP:NONE", "EXTERN ensure_loaded:PROC"]
    externs = []
    for name in names:
        externs.append(f"real_{name}")
        asm.append(f"EXTERN real_{name}:QWORD")
    for ordinal in ordinals:
        externs.append(f"real_ord_{ordinal}")
        asm.append(f"EXTERN real_ord_{ordinal}:QWORD")
    asm.append(".code")

    def proc(label: str, pointer: str, zero: bool) -> None:
        fail = "xor eax, eax" if zero else "mov eax, 80004005h"
        asm.extend([
            f"{label} PROC",
            "    push rcx",
            "    push rdx",
            "    push r8",
            "    push r9",
            "    sub rsp, 28h",
            "    call ensure_loaded",
            "    add rsp, 28h",
            "    pop r9",
            "    pop r8",
            "    pop rdx",
            "    pop rcx",
            f"    mov rax, QWORD PTR [{pointer}]",
            "    test rax, rax",
            "    jz fail_" + label,
            "    jmp rax",
            f"fail_{label}:",
            f"    {fail}",
            "    ret",
            f"{label} ENDP",
        ])

    for name in names:
        proc(name, f"real_{name}", name in ZERO_RETURN)
    for ordinal in ordinals:
        proc(f"ord_{ordinal}", f"real_ord_{ordinal}", False)
    asm.append("END")
    (BUILD / "qtgfx.asm").write_text("\n".join(asm) + "\n", encoding="ascii")

    c_lines = [
        "#define WIN32_LEAN_AND_MEAN",
        "#include <windows.h>",
        "",
    ]
    for name in externs:
        c_lines.append(f"FARPROC {name};")
    c_lines.extend([
        "",
        "static volatile LONG load_state;",
        "",
        "static void load_all(void) {",
        "    HMODULE module;",
    ])
    loads = {
        "d3d11.dll": "d3d11.dll",
        "d3d12.dll": "d3d12.dll",
        "dxgi.dll": "dxgi.dll",
        "d3d9.dll": "d3d9.dll",
        "dwmapi.dll": "dwmapi.dll",
        "dwrite.dll": "dwrite.dll",
        "uxtheme.dll": "uxtheme.dll",
        "api-ms-win-shcore-scaling-l1-1-1.dll": "api-ms-win-shcore-scaling-l1-1-1.dll",
        "api-ms-win-core-winrt-l1-1-0.dll": "api-ms-win-core-winrt-l1-1-0.dll",
        "api-ms-win-core-winrt-string-l1-1-0.dll": "api-ms-win-core-winrt-string-l1-1-0.dll",
        "uiautomationcore.dll": "UIAutomationCore.dll",
    }
    for dll, symbols in symbols_by_dll.items():
        if dll not in loads:
            continue
        c_lines.append(f'    module = LoadLibraryW(L"{loads[dll]}");')
        for symbol in sorted(symbols, key=lambda item: (isinstance(item, str), item)):
            if isinstance(symbol, int):
                c_lines.append(
                    f"    real_ord_{symbol} = module ? GetProcAddress(module, MAKEINTRESOURCEA({symbol})) : NULL;"
                )
            else:
                c_lines.append(
                    f'    real_{symbol} = module ? GetProcAddress(module, "{symbol}") : NULL;'
                )
    c_lines.extend([
        "}",
        "",
        "void ensure_loaded(void) {",
        "    LONG previous = InterlockedCompareExchange(&load_state, 2, 0);",
        "    if (previous == 1 || previous == 2) return;",
        "    load_all();",
        "    InterlockedExchange(&load_state, 1);",
        "}",
        "",
    ])
    (BUILD / "qtgfx.c").write_text("\n".join(c_lines), encoding="ascii")
    exports = list(names)
    for ordinal in ordinals:
        exports.append(f"ord_{ordinal} @{ordinal} NONAME")
    write_def(BUILD / "qtgfx.def", "qtgfx", exports)


def compile_dll(source: Path, definition: Path, output: Path, extra: list[Path] | None = None) -> None:
    command = [
        "cl.exe",
        "/nologo",
        "/O2",
        "/LD",
        "/W3",
        str(source),
        "/link",
        f"/DEF:{definition}",
        f"/OUT:{output}",
    ]
    if extra:
        command[5:5] = [str(item) for item in extra]
    subprocess.check_call(command, cwd=BUILD)


def compile_graphics() -> Path:
    asm = BUILD / "qtgfx.asm"
    obj = BUILD / "qtgfx_asm.obj"
    subprocess.check_call(["ml64.exe", "/nologo", "/c", f"/Fo{obj}", str(asm)], cwd=BUILD)
    output = BUILD / "qtgfx.dll"
    compile_dll(BUILD / "qtgfx.c", BUILD / "qtgfx.def", output, [obj])
    return output


def patch_file(path: Path) -> set[str]:
    blob = bytearray(path.read_bytes())
    pe = pefile.PE(data=bytes(blob), fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
    )
    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        pe.close()
        return set()
    replaced = set()
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        original = entry.dll.decode()
        target = REPLACEMENTS.get(original.lower())
        if not target:
            continue
        if len(target) > len(original):
            raise SystemExit(f"{target} does not fit in {original}")
        offset = pe.get_offset_from_rva(entry.struct.Name)
        end = offset
        while blob[end] != 0:
            end += 1
        encoded = target.encode("ascii")
        blob[offset:offset + len(encoded)] = encoded
        for index in range(offset + len(encoded), end):
            blob[index] = 0
        replaced.add(target)
    pe.close()
    if not replaced:
        return set()
    e_lfanew = int.from_bytes(blob[0x3C:0x40], "little")
    checksum_at = e_lfanew + 24 + 64
    blob[checksum_at:checksum_at + 4] = b"\x00\x00\x00\x00"
    path.write_bytes(blob)
    return replaced


def copy_python_dlls() -> None:
    candidates = [Path(sys.base_prefix), Path(sys.executable).resolve().parent]
    for name in ("python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        source = next((folder / name for folder in candidates if (folder / name).exists()), None)
        if source is None:
            raise SystemExit(f"missing {name} next to Python")
        for folder in packages():
            shutil.copy2(source, folder / name)


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows compatibility DLLs are built on the Windows runner")
    BUILD.mkdir(parents=True, exist_ok=True)
    files = pe_files()
    symbols = collect_symbols(files)
    for key, value in REPLACEMENTS.items():
        if len(value) > len(key):
            raise SystemExit(f"{value} is longer than {key}")
    for dll in ("kernel32.dll", "user32.dll", "api-ms-win-crt-math-l1-1-0.dll"):
        ordinals = sorted(item for item in symbols[dll] if isinstance(item, int))
        if ordinals:
            raise SystemExit(f"{dll} is imported by ordinal: {ordinals}")

    write_def(BUILD / "qtcore32.def", "qtcore32", emit_thunks(
        "qtcore32", [("KERNEL32.dll", symbols["kernel32.dll"])], KERNEL_STUBS,
    ))
    write_def(BUILD / "qtuser.def", "qtuser", emit_thunks(
        "qtuser", [("USER32.dll", symbols["user32.dll"])], USER_STUBS,
    ))
    write_def(BUILD / "qtmath.def", "qtmath", emit_thunks(
        "qtmath",
        [("api-ms-win-crt-math-l1-1-0.dll", symbols["api-ms-win-crt-math-l1-1-0.dll"])],
        {},
    ))
    write_def(BUILD / "qtsynch.def", "qtsynch", list(SYNCH_EXPORTS))
    graphics_sources(symbols)

    built = {}
    thunks = {
        "qtcore32": ROOT / "qtcore32.c",
        "qtuser": ROOT / "qtuser.c",
        "qtmath": ROOT / "qtmath.c",
    }
    for stem, source in thunks.items():
        asm_obj = BUILD / f"{stem}_asm.obj"
        subprocess.check_call(
            ["ml64.exe", "/nologo", "/c", f"/Fo{asm_obj}", str(BUILD / f"{stem}.asm")],
            cwd=BUILD,
        )
        output = BUILD / f"{stem}.dll"
        compile_dll(BUILD / f"{stem}_load.c", BUILD / f"{stem}.def", output, [asm_obj, source])
        built[f"{stem}.dll"] = output
    synch = BUILD / "qtsynch.dll"
    compile_dll(ROOT / "qtsynch.c", BUILD / "qtsynch.def", synch)
    built["qtsynch.dll"] = synch
    graphics = compile_graphics()
    for name in (
        "qtd3d.dll", "qtd12.dll", "qtdx.dll", "qtd9.dll", "qtdwm.dll", "qtdwr.dll",
        "qtuxt.dll", "qtdpi.dll", "qtwinrt.dll", "qtwstr.dll", "qtui.dll",
    ):
        built[name] = graphics

    patched_dirs: set[Path] = set()
    for path in files:
        replaced = patch_file(path)
        if not replaced:
            continue
        patched_dirs.add(path.parent)
        for name in replaced:
            shutil.copy2(built[name], path.parent / name)
    copy_python_dlls()
    print(f"patched {len(patched_dirs)} directories")


if __name__ == "__main__":
    main()
