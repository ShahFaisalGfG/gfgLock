# core - the engine the window and the command line share, free of Qt: the encryption engines
# (native_bridge, py_cipher), the v2 file format (format_v2), one file at a time (file_ops), a run
# over many files (batch), which files a folder gives (scan), plain words for each failure
# (reasons), the password rules (passwords), and the named mutexes (locks). Nothing is imported
# here, so loading one module never loads the native module or the cipher libraries as a side effect.
