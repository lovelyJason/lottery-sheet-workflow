#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>

static HMODULE math_module(void) {
    HMODULE module = GetModuleHandleW(L"api-ms-win-crt-math-l1-1-0.dll");
    if (!module) {
        module = LoadLibraryW(L"api-ms-win-crt-math-l1-1-0.dll");
    }
    return module;
}

static short classify_double(double value) {
    unsigned long long bits;
    unsigned int exponent;
    unsigned long long fraction;
    int negative;
    memcpy(&bits, &value, sizeof(bits));
    exponent = (unsigned int)((bits >> 52) & 0x7ff);
    fraction = bits & 0xfffffffffffffULL;
    negative = (int)(bits >> 63);
    if (exponent == 0x7ff) {
        return fraction ? (short)0x0002 : (negative ? (short)0x0004 : (short)0x0200);
    }
    if (exponent == 0) {
        if (!fraction) {
            return negative ? (short)0x0020 : (short)0x0040;
        }
        return negative ? (short)0x0010 : (short)0x0080;
    }
    return negative ? (short)0x0008 : (short)0x0100;
}

static short classify_float(float value) {
    unsigned int bits;
    unsigned int exponent;
    unsigned int fraction;
    int negative;
    memcpy(&bits, &value, sizeof(bits));
    exponent = (bits >> 23) & 0xff;
    fraction = bits & 0x7fffff;
    negative = (int)(bits >> 31);
    if (exponent == 255) {
        return fraction ? (short)0x0002 : (negative ? (short)0x0004 : (short)0x0200);
    }
    if (exponent == 0) {
        if (!fraction) {
            return negative ? (short)0x0020 : (short)0x0040;
        }
        return negative ? (short)0x0010 : (short)0x0080;
    }
    return negative ? (short)0x0008 : (short)0x0100;
}

short __cdecl compat_dclass(double value) {
    typedef short (__cdecl *Fn)(double);
    HMODULE module = math_module();
    Fn real = module ? (Fn)GetProcAddress(module, "_dclass") : NULL;
    if (real) {
        return real(value);
    }
    return classify_double(value);
}

short __cdecl compat_fdclass(float value) {
    typedef short (__cdecl *Fn)(float);
    HMODULE module = math_module();
    Fn real = module ? (Fn)GetProcAddress(module, "_fdclass") : NULL;
    if (real) {
        return real(value);
    }
    return classify_float(value);
}
