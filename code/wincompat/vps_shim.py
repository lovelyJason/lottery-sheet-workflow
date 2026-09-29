"""Give Qt the few Windows functions a VPS may not have.

The real user32 and d3d11 calls stay direct. Only the missing exports are
forwarded to small stub DLLs, so the window plugin still talks to the system.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
TREE = OUT / "tree"

REPLACEMENTS = {
    "kernel32.dll": "qtcore32.dll",
    "user32.dll": "qtuser.dll",
    "api-ms-win-crt-math-l1-1-0.dll": "qtmath.dll",
    "api-ms-win-core-synch-l1-2-0.dll": "qtsynch.dll",
    "d3d12.dll": "qtd12.dll",
}
KERNEL_STUBS = {
    "SetThreadDescription": "Stub_SetThreadDescription",
    "SetThreadInformation": "Stub_SetThreadInformation",
    "GetCurrentPackageFullName": "Stub_GetCurrentPackageFullName",
}
USER_STUBS = {
    "SetCoalescableTimer": "Stub_SetCoalescableTimer",
    "GetSystemMetricsForDpi": "Stub_GetSystemMetricsForDpi",
    "GetDpiForWindow": "Stub_GetDpiForWindow",
    "AdjustWindowRectExForDpi": "Stub_AdjustWindowRectExForDpi",
    "SystemParametersInfoForDpi": "Stub_SystemParametersInfoForDpi",
}
MATH_STUBS = {"_dclass": "compat_dclass", "_fdclass": "compat_fdclass"}
FORWARD_DLL = {
    "kernel32.dll": "KERNEL32",
    "user32.dll": "USER32",
    "api-ms-win-crt-math-l1-1-0.dll": "api-ms-win-crt-math-l1-1-0",
}
STUB_DLL = {
    "kernel32.dll": "qtcorestub",
    "user32.dll": "qtuserstub",
    "api-ms-win-crt-math-l1-1-0.dll": "qtmathimpl",
}


def packages() -> list[Path]:
    import PySide6
    import shiboken6

    return [Path(PySide6.__file__).resolve().parent, Path(shiboken6.__file__).resolve().parent]


def pe_files() -> list[Path]:
    skip = set(REPLACEMENTS.values())
    found = []
    for package in packages():
        for path in package.rglob("*"):
            if path.suffix.lower() not in {".dll", ".pyd"}:
                continue
            if path.name.lower() in skip:
                continue
            found.append(path)
    return found


def import_map(path: Path) -> dict[str, list[str | int]]:
    pe = pefile.PE(data=path.read_bytes(), fast_load=True)
    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        found: dict[str, list[str | int]] = {}
        if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            return found
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode().lower()
            symbols: list[str | int] = []
            for item in entry.imports:
                if item.name:
                    symbols.append(item.name.decode())
                else:
                    symbols.append(int(item.ordinal))
            found[dll] = symbols
        return found
    finally:
        pe.close()


def write_def(path: Path, library: str, lines: list[str]) -> None:
    path.write_text(
        f"LIBRARY {library}\nEXPORTS\n" + "".join(f"{line}\n" for line in lines),
        encoding="ascii",
    )


def link_forwarder(definition: Path, output: Path) -> None:
    subprocess.check_call(
        [
            "link.exe",
            "/nologo",
            "/DLL",
            "/NOENTRY",
            "/NODEFAULTLIB",
            "/MACHINE:X64",
            f"/DEF:{definition}",
            f"/OUT:{output}",
        ],
        cwd=output.parent,
    )


def compile_stub(source: Path, definition: Path, output: Path) -> None:
    subprocess.check_call(
        [
            "cl.exe",
            "/nologo",
            "/O2",
            "/LD",
            "/W3",
            str(source),
            "/link",
            f"/DEF:{definition}",
            f"/OUT:{output}",
        ],
        cwd=output.parent,
    )


def forward_lines(dll: str, symbols: set[str], stubs: dict[str, str]) -> list[str]:
    lines = []
    for name in sorted(symbols):
        if name in stubs:
            lines.append(f"{name}={STUB_DLL[dll]}.{stubs[name]}")
        else:
            lines.append(f"{name}={FORWARD_DLL[dll]}.{name}")
    return lines


def build_d3d12() -> Path:
    names = ["D3D12SerializeVersionedRootSignature"]
    ordinals = [101, 102]
    asm = ["OPTION CASEMAP:NONE", "EXTERN ensure_loaded:PROC"]
    for name in names:
        asm.append(f"EXTERN real_{name}:QWORD")
    for ordinal in ordinals:
        asm.append(f"EXTERN real_ord_{ordinal}:QWORD")
    asm.append(".code")

    def proc(label: str, pointer: str) -> None:
        asm.extend([
            f"proxy_{label} PROC",
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
            f"    jz fail_{label}",
            "    jmp rax",
            f"fail_{label}:",
            "    mov eax, 80004005h",
            "    ret",
            f"proxy_{label} ENDP",
        ])

    for name in names:
        proc(name, f"real_{name}")
    for ordinal in ordinals:
        proc(f"ord_{ordinal}", f"real_ord_{ordinal}")
    asm.append("END")
    (OUT / "qtd12.asm").write_text("\n".join(asm) + "\n", encoding="ascii")
    c_lines = [
        "#define WIN32_LEAN_AND_MEAN",
        "#include <windows.h>",
        "FARPROC real_D3D12SerializeVersionedRootSignature;",
        "FARPROC real_ord_101;",
        "FARPROC real_ord_102;",
        "static volatile LONG load_state;",
        "static void load_all(void) {",
        '    HMODULE module = LoadLibraryW(L"d3d12.dll");',
        '    real_D3D12SerializeVersionedRootSignature = module ? GetProcAddress(module, "D3D12SerializeVersionedRootSignature") : NULL;',
        "    real_ord_101 = module ? GetProcAddress(module, MAKEINTRESOURCEA(101)) : NULL;",
        "    real_ord_102 = module ? GetProcAddress(module, MAKEINTRESOURCEA(102)) : NULL;",
        "}",
        "void ensure_loaded(void) {",
        "    LONG previous = InterlockedCompareExchange(&load_state, 2, 0);",
        "    if (previous == 1 || previous == 2) return;",
        "    load_all();",
        "    InterlockedExchange(&load_state, 1);",
        "}",
    ]
    (OUT / "qtd12.c").write_text("\n".join(c_lines) + "\n", encoding="ascii")
    write_def(
        OUT / "qtd12.def",
        "qtd12",
        [
            "D3D12SerializeVersionedRootSignature=proxy_D3D12SerializeVersionedRootSignature",
            "proxy_ord_101 @101 NONAME",
            "proxy_ord_102 @102 NONAME",
        ],
    )
    obj = OUT / "qtd12_asm.obj"
    subprocess.check_call(["ml64.exe", "/nologo", "/c", f"/Fo{obj}", str(OUT / "qtd12.asm")], cwd=OUT)
    output = OUT / "qtd12.dll"
    subprocess.check_call(
        [
            "cl.exe",
            "/nologo",
            "/O2",
            "/LD",
            str(OUT / "qtd12.c"),
            str(obj),
            "/link",
            f"/DEF:{OUT / 'qtd12.def'}",
            f"/OUT:{output}",
        ],
        cwd=OUT,
    )
    return output


def mirror(path: Path) -> Path:
    resolved = path.resolve()
    for package in packages():
        try:
            relative = resolved.relative_to(package.parent)
        except ValueError:
            continue
        destination = TREE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination
    raise SystemExit(f"outside Qt packages: {path}")


def patch_names(path: Path, imports: dict[str, list[str | int]]) -> set[str]:
    blob = bytearray(path.read_bytes())
    pe = pefile.PE(data=bytes(blob), fast_load=True)
    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        replaced = set()
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            original = entry.dll.decode()
            target = REPLACEMENTS.get(original.lower())
            if not target or original.lower() not in imports:
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
    finally:
        pe.close()
    if not replaced:
        return set()
    e_lfanew = int.from_bytes(blob[0x3C:0x40], "little")
    blob[e_lfanew + 24 + 64:e_lfanew + 24 + 68] = b"\x00\x00\x00\x00"
    destination = mirror(path)
    destination.write_bytes(blob)
    return replaced


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("run this on the Windows builder")
    OUT.mkdir(parents=True, exist_ok=True)
    parsed = [(path, import_map(path)) for path in pe_files()]

    def needed_dlls(imports: dict[str, list[str | int]]) -> set[str]:
        needed = set()
        if any(name in KERNEL_STUBS for name in imports.get("kernel32.dll", []) if isinstance(name, str)):
            needed.add("kernel32.dll")
        if any(name in USER_STUBS for name in imports.get("user32.dll", []) if isinstance(name, str)):
            needed.add("user32.dll")
        if "api-ms-win-crt-math-l1-1-0.dll" in imports:
            needed.add("api-ms-win-crt-math-l1-1-0.dll")
        if "api-ms-win-core-synch-l1-2-0.dll" in imports:
            needed.add("api-ms-win-core-synch-l1-2-0.dll")
        if "d3d12.dll" in imports:
            needed.add("d3d12.dll")
        return needed

    kernel_symbols: set[str] = set()
    user_symbols: set[str] = set()
    math_symbols: set[str] = set()
    for _path, imports in parsed:
        needed = needed_dlls(imports)
        for dll, bucket in (
            ("kernel32.dll", kernel_symbols),
            ("user32.dll", user_symbols),
            ("api-ms-win-crt-math-l1-1-0.dll", math_symbols),
        ):
            if dll not in needed:
                continue
            for symbol in imports.get(dll, []):
                if isinstance(symbol, int):
                    raise SystemExit(f"{dll} ordinal import {symbol}")
                bucket.add(symbol)

    write_def(OUT / "qtcore32.def", "qtcore32", forward_lines("kernel32.dll", kernel_symbols, KERNEL_STUBS))
    write_def(OUT / "qtuser.def", "qtuser", forward_lines("user32.dll", user_symbols, USER_STUBS))
    write_def(OUT / "qtmath.def", "qtmath", forward_lines("api-ms-win-crt-math-l1-1-0.dll", math_symbols, MATH_STUBS))
    write_def(OUT / "qtcorestub.def", "qtcorestub", list(KERNEL_STUBS.values()))
    write_def(OUT / "qtuserstub.def", "qtuserstub", list(USER_STUBS.values()))
    write_def(OUT / "qtmathimpl.def", "qtmathimpl", list(MATH_STUBS.values()))
    write_def(OUT / "qtsynch.def", "qtsynch", ["WaitOnAddress", "WakeByAddressSingle", "WakeByAddressAll"])

    link_forwarder(OUT / "qtcore32.def", OUT / "qtcore32.dll")
    link_forwarder(OUT / "qtuser.def", OUT / "qtuser.dll")
    link_forwarder(OUT / "qtmath.def", OUT / "qtmath.dll")
    compile_stub(ROOT / "qtcore32.c", OUT / "qtcorestub.def", OUT / "qtcorestub.dll")
    compile_stub(ROOT / "qtuser.c", OUT / "qtuserstub.def", OUT / "qtuserstub.dll")
    compile_stub(ROOT / "qtmath.c", OUT / "qtmathimpl.def", OUT / "qtmathimpl.dll")
    compile_stub(ROOT / "qtsynch.c", OUT / "qtsynch.def", OUT / "qtsynch.dll")
    build_d3d12()

    companions = {
        "qtcore32.dll": ["qtcore32.dll", "qtcorestub.dll"],
        "qtuser.dll": ["qtuser.dll", "qtuserstub.dll"],
        "qtmath.dll": ["qtmath.dll", "qtmathimpl.dll"],
        "qtsynch.dll": ["qtsynch.dll"],
        "qtd12.dll": ["qtd12.dll"],
    }
    patched = 0
    for path, imports in parsed:
        needed = needed_dlls(imports)
        if not needed:
            continue
        replaced = patch_names(path, {dll: imports[dll] for dll in needed})
        destination = mirror(path)
        for name in replaced:
            for filename in companions[name]:
                shutil.copy2(OUT / filename, destination.parent / filename)
        patched += 1
    copy_system_runtime()
    print(f"patched {patched} Qt binaries into {TREE}")


def copy_system_runtime() -> None:
    """Ship the Universal CRT beside Qt. A VPS often does not have it installed."""
    kits = Path(r"C:\Program Files (x86)\Windows Kits\10\Redist\ucrt\DLLs\x64")
    if not kits.is_dir():
        found = list(Path(r"C:\Program Files (x86)\Windows Kits\10").glob("Redist/**/ucrt/DLLs/x64"))
        if not found:
            raise SystemExit("Universal CRT redistributable was not found")
        kits = found[0]
    destinations = [TREE, TREE / "PySide6", TREE / "shiboken6"]
    for folder in destinations:
        folder.mkdir(parents=True, exist_ok=True)
        for source in kits.glob("*.dll"):
            shutil.copy2(source, folder / source.name)


if __name__ == "__main__":
    main()
