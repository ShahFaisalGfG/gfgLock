import os
import shlex
import sys
from multiprocessing import freeze_support

from PyQt6 import QtWidgets, QtGui

from utils import apply_theme
from utils import resource_path
from views.main_window import MainWindow
from views.encrypt_dialog import EncryptDialog

# === PYINSTALLER SHELL ARGUMENT FIX - MUST BE HERE! ===
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    import ctypes
    from ctypes import wintypes
    try:
        GetCommandLineW = ctypes.windll.kernel32.GetCommandLineW
        GetCommandLineW.argtypes = []
        GetCommandLineW.restype = wintypes.LPCWSTR

        CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
        CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)

        cmd = GetCommandLineW()
        argc = ctypes.c_int()
        argv = CommandLineToArgvW(cmd, ctypes.byref(argc))
        sys.argv = [argv[i] for i in range(argc.value)]
        if sys.argv:
            sys.argv[0] = sys.executable
    except:
        pass
# ========================================================

os.environ["QT_QPA_PLATFORM"] = "windows"
# ... rest of your code



# ========================================================
# ========================================================

def main():
    app = QtWidgets.QApplication(sys.argv)
    freeze_support()
    app.setStyle("Fusion")
    app.setWindowIcon(QtGui.QIcon(resource_path("./assets/icons/gfgLock.png")))

    # Apply theme
    apply_theme(app)

    args = sys.argv[1:]
    debug_logs = [f"Raw args received: {args}"]

    # No args → normal launch
    if not args:
        win = MainWindow()
        win.show()
        sys.exit(app.exec())

    # === Detect operation mode ===
    mode = None
    path_args = args

    if args and args[0].lower() in ("encrypt", "decrypt"):
        mode = args[0].lower()
        path_args = args[1:]
        debug_logs.append(f"Explicit mode: {mode}")
    else:
        # Auto-detect: if any encrypted file exists in args → decrypt
        enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
        enc_files = [p for p in args if os.path.exists(p) and p.lower().endswith(enc_exts)]
        if enc_files:
            mode = "decrypt"
            debug_logs.append("Auto-detected decrypt mode (encrypted files found)")

    # If no valid mode → open main window
    if not mode:
        debug_logs.append("No valid mode → opening main window")
        win = MainWindow()
        win.show_logs("\n".join(debug_logs))
        win.show()
        sys.exit(app.exec())

    # === Reconstruct paths correctly (Windows Explorer breaks paths with spaces) ===
    raw_paths = []

    if path_args:
        combined = " ".join(path_args)
        debug_logs.append(f"Combined path string: {combined}")

        # First: try if the combined string is a real path
        if os.path.exists(combined):
            raw_paths = [combined]
            debug_logs.append("Combined path exists → using as single item")
        else:
            # Second: try shlex (handles quoted paths like "C:\My Folder\file.gfglock")
            try:
                raw_paths = shlex.split(combined)
                debug_logs.append(f"shlex parsed: {raw_paths}")
            except:
                raw_paths = path_args  # fallback

            # Final fallback: if nothing works, treat as one broken path
            if not any(os.path.exists(p.strip('"')) for p in raw_paths):
                raw_paths = [combined]
                debug_logs.append("Fallback: treating all args as one broken path")

    # === Expand folders and collect only real files (especially .gfglock for decrypt) ===
    final_paths = []

    for path in raw_paths:
        p = path.strip('"\'')
        abs_p = os.path.abspath(p)

        if not os.path.exists(abs_p):
            final_paths.append(abs_p)  # keep for error visibility
            continue

        # Only include files appropriate for the selected mode:
        enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
        if os.path.isfile(abs_p):
            # Encrypt mode: skip files that are already encrypted
            if mode == "encrypt":
                if abs_p.lower().endswith(enc_exts):
                    continue
            # Decrypt mode: include only encrypted files
            else:
                if not abs_p.lower().endswith(enc_exts):
                    continue
            final_paths.append(abs_p)

        elif os.path.isdir(abs_p):
            for root, _, files in os.walk(abs_p):
                for f in files:
                    fp = os.path.join(root, f)
                    if mode == "encrypt":
                        # In encrypt mode, skip files that already have an encrypted extension
                        if fp.lower().endswith(enc_exts):
                            continue
                    else:
                        # In decrypt mode, only include encrypted files
                        if not fp.lower().endswith(enc_exts):
                            continue
                    final_paths.append(fp)

    # Remove duplicates
    seen = set()
    unique_paths = [p for p in final_paths if not (p in seen or seen.add(p))]

    debug_logs.append(f"Final files to process: {unique_paths}")

    # === Launch dialog ===
    dlg = EncryptDialog(None, mode)

    for p in unique_paths:
        dlg.add_path_to_list(p)

    if unique_paths:
        dlg.pass_input.setFocus()
    else:
        from widgets.custom_title_bar import show_message
        show_message(None, "No files", f"No valid files found for {mode}ion.", icon="warning")

    dlg.exec()
    sys.exit(0)


if __name__ == "__main__":
    main()