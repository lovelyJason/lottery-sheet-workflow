#define WIN32_LEAN_AND_MEAN
#include <windows.h>

HRESULT WINAPI Stub_SetThreadDescription(HANDLE thread, PCWSTR name) {
    typedef HRESULT (WINAPI *Fn)(HANDLE, PCWSTR);
    Fn real = (Fn)GetProcAddress(GetModuleHandleW(L"KERNEL32.dll"), "SetThreadDescription");
    if (real) {
        return real(thread, name);
    }
    return S_OK;
}

BOOL WINAPI Stub_SetThreadInformation(HANDLE thread, int kind, void *info, DWORD size) {
    typedef BOOL (WINAPI *Fn)(HANDLE, int, void *, DWORD);
    Fn real = (Fn)GetProcAddress(GetModuleHandleW(L"KERNEL32.dll"), "SetThreadInformation");
    if (real) {
        return real(thread, kind, info, size);
    }
    SetLastError(ERROR_CALL_NOT_IMPLEMENTED);
    return FALSE;
}

LONG WINAPI Stub_GetCurrentPackageFullName(UINT32 *length, WCHAR *buffer) {
    typedef LONG (WINAPI *Fn)(UINT32 *, WCHAR *);
    Fn real = (Fn)GetProcAddress(GetModuleHandleW(L"KERNEL32.dll"), "GetCurrentPackageFullName");
    if (real) {
        return real(length, buffer);
    }
    if (length) {
        *length = 0;
    }
    return 15700L;
}
