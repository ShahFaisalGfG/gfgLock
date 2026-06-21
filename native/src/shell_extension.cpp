// shell_extension.cpp - IExplorerCommand COM in-process server
// Provides "Encrypt with gfgLock" and "Decrypt with gfgLock" in the
// Windows 11 first-level context menu via ExplorerCommandHandler.

#define WIN32_LEAN_AND_MEAN
#define STRICT
#include <windows.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <objbase.h>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

static HMODULE g_hModule  = nullptr;
static LONG    g_refCount = 0;

// ---------------------------------------------------------------------------
// CLSIDs
// {E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}  - Encrypt
// {F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}  - Decrypt
// ---------------------------------------------------------------------------

static const GUID CLSID_GfgLockEncrypt = {
    0xE1D4C8A3, 0x2B57, 0x4F6E,
    {0x9D, 0x3A, 0xF5, 0xC7, 0x82, 0x10, 0x94, 0xBE}
};
static const GUID CLSID_GfgLockDecrypt = {
    0xF2E5D9B4, 0x3C68, 0x4A7F,
    {0xBE, 0x4B, 0x06, 0xD8, 0x93, 0x21, 0x05, 0xCF}
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static std::wstring dllDirectory()
{
    wchar_t buf[MAX_PATH] = {};
    GetModuleFileNameW(g_hModule, buf, MAX_PATH);
    std::wstring s(buf);
    auto pos = s.rfind(L'\\');
    if (pos != std::wstring::npos) s.resize(pos);
    return s;
}

static std::wstring quoted(const std::wstring& s)
{
    return L"\"" + s + L"\"";
}

// Convert a wide string to UTF-8.
static std::string toUtf8(const std::wstring& w)
{
    if (w.empty()) return {};
    int len = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (len <= 0) return {};
    std::string s(len - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, s.data(), len, nullptr, nullptr);
    return s;
}

// Write paths (UTF-8, one per line) to a temp file; return the temp file path.
static std::wstring writeTempFile(const std::vector<std::wstring>& paths)
{
    wchar_t tmp[MAX_PATH] = {};
    wchar_t dir[MAX_PATH] = {};
    GetTempPathW(MAX_PATH, dir);
    GetTempFileNameW(dir, L"gfg", 0, tmp);

    HANDLE h = CreateFileW(tmp, GENERIC_WRITE, 0, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) return {};
    for (const auto& p : paths) {
        std::string line = toUtf8(p) + "\n";
        DWORD written = 0;
        WriteFile(h, line.c_str(), static_cast<DWORD>(line.size()), &written, nullptr);
    }
    CloseHandle(h);
    return tmp;
}

// ---------------------------------------------------------------------------
// GfgLockCommand - IExplorerCommand + IUnknown
// ---------------------------------------------------------------------------

class GfgLockCommand : public IExplorerCommand
{
    LONG _refs;
    bool _isEncrypt;

public:
    explicit GfgLockCommand(bool encrypt)
        : _refs(1), _isEncrypt(encrypt)
    {
        InterlockedIncrement(&g_refCount);
    }

    ~GfgLockCommand()
    {
        InterlockedDecrement(&g_refCount);
    }

    // ── IUnknown ──────────────────────────────────────────────────────────

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override
    {
        if (!ppv) return E_POINTER;
        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IExplorerCommand)) {
            *ppv = static_cast<IExplorerCommand*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override
    {
        return InterlockedIncrement(&_refs);
    }

    STDMETHODIMP_(ULONG) Release() override
    {
        LONG r = InterlockedDecrement(&_refs);
        if (r == 0) delete this;
        return r;
    }

    // ── IExplorerCommand ──────────────────────────────────────────────────

    STDMETHODIMP GetTitle(IShellItemArray*, LPWSTR* ppszName) override
    {
        if (!ppszName) return E_POINTER;
        const wchar_t* title = _isEncrypt ? L"Encrypt with gfgLock"
                                           : L"Decrypt with gfgLock";
        size_t len = wcslen(title) + 1;
        *ppszName = static_cast<LPWSTR>(CoTaskMemAlloc(len * sizeof(wchar_t)));
        if (!*ppszName) return E_OUTOFMEMORY;
        wcscpy_s(*ppszName, len, title);
        return S_OK;
    }

    STDMETHODIMP GetIcon(IShellItemArray*, LPWSTR* ppszIcon) override
    {
        if (!ppszIcon) return E_POINTER;
        std::wstring icon = dllDirectory() + L"\\icons\\gfgLock.ico";
        size_t len = icon.size() + 1;
        *ppszIcon = static_cast<LPWSTR>(CoTaskMemAlloc(len * sizeof(wchar_t)));
        if (!*ppszIcon) return E_OUTOFMEMORY;
        wcscpy_s(*ppszIcon, len, icon.c_str());
        return S_OK;
    }

    STDMETHODIMP GetToolTip(IShellItemArray*, LPWSTR* ppszInfotip) override
    {
        if (!ppszInfotip) return E_POINTER;
        *ppszInfotip = nullptr;
        return E_NOTIMPL;
    }

    STDMETHODIMP GetCanonicalName(GUID* pguid) override
    {
        if (!pguid) return E_POINTER;
        *pguid = _isEncrypt ? CLSID_GfgLockEncrypt : CLSID_GfgLockDecrypt;
        return S_OK;
    }

    STDMETHODIMP GetState(IShellItemArray*, BOOL, EXPCMDSTATE* pState) override
    {
        if (!pState) return E_POINTER;
        *pState = ECS_ENABLED;
        return S_OK;
    }

    STDMETHODIMP GetFlags(EXPCMDFLAGS* pFlags) override
    {
        if (!pFlags) return E_POINTER;
        *pFlags = ECF_DEFAULT;
        return S_OK;
    }

    STDMETHODIMP EnumSubCommands(IEnumExplorerCommand** ppEnum) override
    {
        if (!ppEnum) return E_POINTER;
        *ppEnum = nullptr;
        return E_NOTIMPL;
    }

    STDMETHODIMP Invoke(IShellItemArray* psia, IBindCtx*) override
    {
        std::wstring exePath = dllDirectory() + L"\\gfgLock.exe";
        std::wstring mode    = _isEncrypt ? L"encrypt" : L"decrypt";

        std::vector<std::wstring> paths;
        if (psia) {
            DWORD count = 0;
            psia->GetCount(&count);
            paths.reserve(count);
            for (DWORD i = 0; i < count; i++) {
                IShellItem* psi = nullptr;
                if (SUCCEEDED(psia->GetItemAt(i, &psi))) {
                    LPWSTR disp = nullptr;
                    if (SUCCEEDED(psi->GetDisplayName(SIGDN_FILESYSPATH, &disp))) {
                        paths.emplace_back(disp);
                        CoTaskMemFree(disp);
                    }
                    psi->Release();
                }
            }
        }

        std::wstring cmdLine = buildCmdLine(exePath, mode, paths);

        STARTUPINFOW si      = {};
        si.cb                = sizeof(si);
        PROCESS_INFORMATION pi = {};
        CreateProcessW(nullptr,
                       cmdLine.data(),
                       nullptr, nullptr,
                       FALSE,
                       CREATE_NO_WINDOW,
                       nullptr, nullptr,
                       &si, &pi);
        if (pi.hProcess) CloseHandle(pi.hProcess);
        if (pi.hThread)  CloseHandle(pi.hThread);
        return S_OK;
    }

private:
    // Build the command line; fall back to @responsefile if it would be too long.
    std::wstring buildCmdLine(const std::wstring& exe,
                              const std::wstring& mode,
                              const std::vector<std::wstring>& paths) const
    {
        std::wstring direct = quoted(exe) + L" " + mode;
        for (const auto& p : paths) {
            direct += L" ";
            direct += quoted(p);
        }
        if (direct.size() < 8000)
            return direct;

        std::wstring tmp = writeTempFile(paths);
        if (tmp.empty()) return direct;
        return quoted(exe) + L" " + mode + L" @" + quoted(tmp);
    }
};

// ---------------------------------------------------------------------------
// GfgLockClassFactory - IClassFactory
// ---------------------------------------------------------------------------

class GfgLockClassFactory : public IClassFactory
{
    LONG _refs;
    bool _isEncrypt;

public:
    explicit GfgLockClassFactory(bool encrypt)
        : _refs(1), _isEncrypt(encrypt)
    {
        InterlockedIncrement(&g_refCount);
    }

    ~GfgLockClassFactory()
    {
        InterlockedDecrement(&g_refCount);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override
    {
        if (!ppv) return E_POINTER;
        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IClassFactory)) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&_refs); }

    STDMETHODIMP_(ULONG) Release() override
    {
        LONG r = InterlockedDecrement(&_refs);
        if (r == 0) delete this;
        return r;
    }

    // IClassFactory
    STDMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) override
    {
        if (!ppv) return E_POINTER;
        if (outer) return CLASS_E_NOAGGREGATION;
        auto* cmd = new (std::nothrow) GfgLockCommand(_isEncrypt);
        if (!cmd) return E_OUTOFMEMORY;
        HRESULT hr = cmd->QueryInterface(riid, ppv);
        cmd->Release();
        return hr;
    }

    STDMETHODIMP LockServer(BOOL lock) override
    {
        lock ? InterlockedIncrement(&g_refCount) : InterlockedDecrement(&g_refCount);
        return S_OK;
    }
};

// ---------------------------------------------------------------------------
// DLL entry points
// ---------------------------------------------------------------------------

BOOL APIENTRY DllMain(HMODULE hModule, DWORD fdwReason, LPVOID)
{
    if (fdwReason == DLL_PROCESS_ATTACH) {
        g_hModule = hModule;
        DisableThreadLibraryCalls(hModule);
    }
    return TRUE;
}

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** ppv)
{
    if (!ppv) return E_POINTER;
    IClassFactory* factory = nullptr;
    if (IsEqualCLSID(clsid, CLSID_GfgLockEncrypt))
        factory = new (std::nothrow) GfgLockClassFactory(true);
    else if (IsEqualCLSID(clsid, CLSID_GfgLockDecrypt))
        factory = new (std::nothrow) GfgLockClassFactory(false);
    else
        return CLASS_E_CLASSNOTAVAILABLE;

    if (!factory) return E_OUTOFMEMORY;
    HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}

STDAPI DllCanUnloadNow()
{
    return g_refCount == 0 ? S_OK : S_FALSE;
}
