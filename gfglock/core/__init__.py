# core - the encryption engines (native_bridge, py_cipher), the v2 file format (format_v2), and the
# file-level operations built on them (file_ops). Nothing is imported here, so loading one module
# never loads the native module or the cipher libraries as a side effect.
