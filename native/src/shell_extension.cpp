// shell_extension.cpp - IExplorerCommand COM in-process server
// Provides "Encrypt with gfgLock" and "Decrypt with gfgLock" in the
// Windows 11 first-level context menu via ExplorerCommandHandler.

#define WIN32_LEAN_AND_MEAN
#define STRICT
#include <windows.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <objbase.h>
#include <wrl/client.h>
#include <cwctype>
#include <memory>
#include <new>
#include <string>
#include <utility>
#include <vector>

using Microsoft::WRL::ComPtr;

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

// COM methods must never let a C++ exception reach Explorer: an allocation failure becomes
// E_OUTOFMEMORY and anything else E_FAIL.
template<typename Fn>
static HRESULT guarded(Fn&& fn) noexcept
{
    try {
        return fn();
    } catch (const std::bad_alloc&) {
        return E_OUTOFMEMORY;
    } catch (...) {
        return E_FAIL;
    }
}

struct CoTaskMemDeleter {
    void operator()(wchar_t* p) const noexcept { CoTaskMemFree(p); }
};
using CoTaskString = std::unique_ptr<wchar_t, CoTaskMemDeleter>;

// Copy text into a CoTaskMemAlloc buffer, which the caller (Explorer) frees.
static HRESULT coTaskCopy(const wchar_t* text, LPWSTR* out)
{
    size_t len = wcslen(text) + 1;
    *out = static_cast<LPWSTR>(CoTaskMemAlloc(len * sizeof(wchar_t)));
    if (!*out) return E_OUTOFMEMORY;
    wcscpy_s(*out, len, text);
    return S_OK;
}

// The item's filesystem path, or an empty string for items that have none (Control Panel
// entries, files inside a zip folder, and other virtual items).
static std::wstring filesystemPath(IShellItem* item)
{
    LPWSTR raw = nullptr;
    if (FAILED(item->GetDisplayName(SIGDN_FILESYSPATH, &raw)) || !raw) return {};
    CoTaskString path(raw);
    return path.get();
}

// Call fn(item) for each item of the selection until it returns false.
template<typename Fn>
static void forEachItem(IShellItemArray* items, Fn&& fn)
{
    DWORD count = 0;
    if (!items || FAILED(items->GetCount(&count))) return;
    for (DWORD i = 0; i < count; i++) {
        ComPtr<IShellItem> item;
        if (SUCCEEDED(items->GetItemAt(i, &item)) && !fn(item.Get())) break;
    }
}

// The selection's filesystem paths; virtual items are left out.
static std::vector<std::wstring> filesystemPaths(IShellItemArray* items)
{
    std::vector<std::wstring> paths;
    forEachItem(items, [&](IShellItem* item) {
        std::wstring path = filesystemPath(item);
        if (!path.empty()) paths.push_back(std::move(path));
        return true;
    });
    return paths;
}

static std::wstring dllDirectory()
{
    // Grow the buffer for install paths longer than MAX_PATH instead of truncating them.
    std::wstring s(MAX_PATH, L'\0');
    for (;;) {
        DWORD n = GetModuleFileNameW(g_hModule, s.data(), static_cast<DWORD>(s.size()));
        if (n == 0) return {};
        if (n < s.size()) { s.resize(n); break; }
        s.resize(s.size() * 2);
    }
    auto pos = s.rfind(L'\\');
    if (pos != std::wstring::npos) s.resize(pos);
    return s;
}

// True when the path ends in one of gfgLock's encrypted extensions (any letter case). A dot in
// a folder name leaves a backslash in the "extension", so it never matches.
static bool hasEncryptedExtension(const std::wstring& path)
{
    auto dot = path.rfind(L'.');
    if (dot == std::wstring::npos) return false;
    std::wstring ext = path.substr(dot);
    for (auto& ch : ext) ch = static_cast<wchar_t>(towlower(ch));
    return ext == L".gfglock" || ext == L".gfglck" || ext == L".gfgcha";
}

// Quote one command-line argument. CommandLineToArgvW reads backslashes right before a quote as
// escapes, so trailing ones are doubled: D:\ is passed as "D:\\" and reaches the app as D:\
// instead of D:". Windows paths can't contain quotes, so nothing else needs escaping.
static std::wstring quoted(const std::wstring& s)
{
    size_t trailing = 0;
    while (trailing < s.size() && s[s.size() - 1 - trailing] == L'\\') trailing++;
    return L"\"" + s + std::wstring(trailing, L'\\') + L"\"";
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

// Write paths (UTF-8, one per line) to a temp file; return the temp file path, or an empty
// string when it can't be written. The text is built first, so a failed allocation can't leave
// a handle open.
static std::wstring writeTempFile(const std::vector<std::wstring>& paths)
{
    std::string text;
    for (const auto& p : paths) {
        text += toUtf8(p);
        text += '\n';
    }
    if (text.size() > MAXDWORD) return {};

    wchar_t tmp[MAX_PATH] = {};
    wchar_t dir[MAX_PATH] = {};
    DWORD dirLen = GetTempPathW(MAX_PATH, dir);
    if (dirLen == 0 || dirLen > MAX_PATH || !GetTempFileNameW(dir, L"gfg", 0, tmp)) return {};

    HANDLE h = CreateFileW(tmp, GENERIC_WRITE, 0, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) {
        DeleteFileW(tmp);
        return {};
    }
    DWORD written = 0;
    bool ok = WriteFile(h, text.data(), static_cast<DWORD>(text.size()), &written, nullptr)
              && written == text.size();
    CloseHandle(h);
    if (!ok) {
        DeleteFileW(tmp);
        return {};
    }
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
        return coTaskCopy(_isEncrypt ? L"Encrypt with gfgLock" : L"Decrypt with gfgLock", ppszName);
    }

    STDMETHODIMP GetIcon(IShellItemArray*, LPWSTR* ppszIcon) override
    {
        if (!ppszIcon) return E_POINTER;
        *ppszIcon = nullptr;
        return guarded([&] {
            std::wstring icon = dllDirectory() + L"\\icons\\gfgLock.ico";
            return coTaskCopy(icon.c_str(), ppszIcon);
        });
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

    STDMETHODIMP GetState(IShellItemArray* psia, BOOL fOkToBeSlow, EXPCMDSTATE* pState) override
    {
        if (!pState) return E_POINTER;
        *pState = ECS_ENABLED;
        if (!psia) return S_OK;
        // Inspecting the selection can touch slow (network) items; ask Explorer to call
        // again on its background thread rather than delaying the menu.
        if (!fOkToBeSlow) return E_PENDING;

        return guarded([&] {
            // Items without a filesystem path count as neither kind, so a selection of only
            // virtual items hides both commands.
            bool anyEncrypted = false, anyPlain = false;
            forEachItem(psia, [&](IShellItem* item) {
                std::wstring path = filesystemPath(item);
                if (path.empty()) return true;
                SFGAOF attrs = 0;
                item->GetAttributes(SFGAO_FOLDER | SFGAO_STREAM, &attrs);
                if ((attrs & SFGAO_FOLDER) && !(attrs & SFGAO_STREAM))
                    anyEncrypted = anyPlain = true;  // a folder can hold either kind
                else
                    (hasEncryptedExtension(path) ? anyEncrypted : anyPlain) = true;
                return !(anyEncrypted && anyPlain);
            });
            if (_isEncrypt ? !anyPlain : !anyEncrypted) *pState = ECS_HIDDEN;
            return S_OK;
        });
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
        return guarded([&]() -> HRESULT {
            std::vector<std::wstring> paths = filesystemPaths(psia);
            if (paths.empty()) return S_OK;  // nothing gfgLock could open

            std::wstring exePath = dllDirectory() + L"\\gfgLock.exe";
            std::wstring mode    = _isEncrypt ? L"encrypt" : L"decrypt";
            std::wstring responseFile;
            std::wstring cmdLine = buildCmdLine(exePath, mode, paths, responseFile);

            STARTUPINFOW si      = {};
            si.cb                = sizeof(si);
            PROCESS_INFORMATION pi = {};
            if (!CreateProcessW(nullptr,
                                cmdLine.data(),
                                nullptr, nullptr,
                                FALSE,
                                CREATE_NO_WINDOW,
                                nullptr, nullptr,
                                &si, &pi)) {
                HRESULT hr = HRESULT_FROM_WIN32(GetLastError());
                // The app normally deletes the response file after reading it; it never started.
                if (!responseFile.empty()) DeleteFileW(responseFile.c_str());
                return hr;
            }
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            return S_OK;
        });
    }

private:
    // Build the command line; fall back to @responsefile if it would be too long.
    std::wstring buildCmdLine(const std::wstring& exe,
                              const std::wstring& mode,
                              const std::vector<std::wstring>& paths,
                              std::wstring& responseFile) const
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
        responseFile = tmp;
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
