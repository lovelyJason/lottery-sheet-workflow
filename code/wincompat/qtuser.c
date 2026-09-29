#define WIN32_LEAN_AND_MEAN
#include <windows.h>

UINT_PTR WINAPI Stub_SetCoalescableTimer(HWND hwnd, UINT_PTR id, UINT elapse,
                                        TIMERPROC proc, ULONG tolerance) {
    typedef UINT_PTR (WINAPI *Fn)(HWND, UINT_PTR, UINT, TIMERPROC, ULONG);
    typedef UINT_PTR (WINAPI *TimerFn)(HWND, UINT_PTR, UINT, TIMERPROC);
    HMODULE user = GetModuleHandleW(L"USER32.dll");
    Fn real = user ? (Fn)GetProcAddress(user, "SetCoalescableTimer") : NULL;
    if (real) {
        return real(hwnd, id, elapse, proc, tolerance);
    }
    TimerFn timer = user ? (TimerFn)GetProcAddress(user, "SetTimer") : NULL;
    return timer ? timer(hwnd, id, elapse, proc) : 0;
}

int WINAPI Stub_GetSystemMetricsForDpi(int index, UINT dpi) {
    typedef int (WINAPI *Fn)(int, UINT);
    HMODULE user = GetModuleHandleW(L"USER32.dll");
    Fn real = user ? (Fn)GetProcAddress(user, "GetSystemMetricsForDpi") : NULL;
    if (real) {
        return real(index, dpi);
    }
    typedef int (WINAPI *MetricsFn)(int);
    MetricsFn metrics = user ? (MetricsFn)GetProcAddress(user, "GetSystemMetrics") : NULL;
    return metrics ? metrics(index) : 0;
}

UINT WINAPI Stub_GetDpiForWindow(HWND hwnd) {
    typedef UINT (WINAPI *Fn)(HWND);
    HMODULE user = GetModuleHandleW(L"USER32.dll");
    Fn real = user ? (Fn)GetProcAddress(user, "GetDpiForWindow") : NULL;
    if (real) {
        return real(hwnd);
    }
    return 96;
}

BOOL WINAPI Stub_AdjustWindowRectExForDpi(RECT *rect, DWORD style, BOOL menu,
                                          DWORD extra, UINT dpi) {
    typedef BOOL (WINAPI *Fn)(RECT *, DWORD, BOOL, DWORD, UINT);
    typedef BOOL (WINAPI *OldFn)(RECT *, DWORD, BOOL, DWORD);
    HMODULE user = GetModuleHandleW(L"USER32.dll");
    Fn real = user ? (Fn)GetProcAddress(user, "AdjustWindowRectExForDpi") : NULL;
    if (real) {
        return real(rect, style, menu, extra, dpi);
    }
    OldFn older = user ? (OldFn)GetProcAddress(user, "AdjustWindowRectEx") : NULL;
    return older ? older(rect, style, menu, extra) : FALSE;
}

BOOL WINAPI Stub_SystemParametersInfoForDpi(UINT action, UINT param, PVOID data,
                                            UINT winini, UINT dpi) {
    typedef BOOL (WINAPI *Fn)(UINT, UINT, PVOID, UINT, UINT);
    typedef BOOL (WINAPI *InfoFn)(UINT, UINT, PVOID, UINT);
    HMODULE user = GetModuleHandleW(L"USER32.dll");
    Fn real = user ? (Fn)GetProcAddress(user, "SystemParametersInfoForDpi") : NULL;
    if (real) {
        return real(action, param, data, winini, dpi);
    }
    InfoFn info = user ? (InfoFn)GetProcAddress(user, "SystemParametersInfoW") : NULL;
    return info ? info(action, param, data, winini) : FALSE;
}
