#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static BOOL (WINAPI *real_wait)(volatile VOID *, PVOID, SIZE_T, DWORD);
static VOID (WINAPI *real_wake_one)(PVOID);
static VOID (WINAPI *real_wake_all)(PVOID);
static int resolved;

static void resolve(void) {
    HMODULE module;
    if (resolved) {
        return;
    }
    resolved = 1;
    module = GetModuleHandleW(L"api-ms-win-core-synch-l1-2-0.dll");
    if (!module) {
        module = LoadLibraryW(L"api-ms-win-core-synch-l1-2-0.dll");
    }
    if (!module) {
        return;
    }
    real_wait = (void *)GetProcAddress(module, "WaitOnAddress");
    real_wake_one = (void *)GetProcAddress(module, "WakeByAddressSingle");
    real_wake_all = (void *)GetProcAddress(module, "WakeByAddressAll");
}

static int same_bits(volatile VOID *address, PVOID compare, SIZE_T size) {
    if (size == 1) {
        return *(volatile unsigned char *)address == *(unsigned char *)compare;
    }
    if (size == 2) {
        return *(volatile unsigned short *)address == *(unsigned short *)compare;
    }
    if (size == 4) {
        return *(volatile unsigned int *)address == *(unsigned int *)compare;
    }
    if (size == 8) {
        return *(volatile unsigned long long *)address == *(unsigned long long *)compare;
    }
    return 0;
}

BOOL WINAPI WaitOnAddress(volatile VOID *address, PVOID compare, SIZE_T size, DWORD milliseconds) {
    DWORD start;
    resolve();
    if (real_wait) {
        return real_wait(address, compare, size, milliseconds);
    }
    start = GetTickCount();
    for (;;) {
        if (!same_bits(address, compare, size)) {
            return TRUE;
        }
        if (milliseconds == 0) {
            return FALSE;
        }
        if (milliseconds != INFINITE && GetTickCount() - start >= milliseconds) {
            return FALSE;
        }
        Sleep(1);
    }
}

VOID WINAPI WakeByAddressSingle(PVOID address) {
    resolve();
    if (real_wake_one) {
        real_wake_one(address);
    }
}

VOID WINAPI WakeByAddressAll(PVOID address) {
    resolve();
    if (real_wake_all) {
        real_wake_all(address);
    }
}
