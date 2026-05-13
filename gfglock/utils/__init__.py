# utils — public API for gfglock utility modules

from gfglock.utils.helpers import (
    resource_path,
    get_cpu_thread_count,
    clamp_threads,
    format_duration,
    format_bytes,
    format_time,
    choose_scale,
    calculate_files_total_size,
    predict_encrypted_size,
    derive_key,
    safe_print,
    generate_encrypted_name,
)
from gfglock.utils.settings import (
    get_settings_file,
    get_default_settings,
    load_settings,
    merge_settings,
    save_settings,
)
from gfglock.utils.logging import (
    get_logs_dir,
    get_critical_log_file,
    get_general_log_file,
    write_critical_log,
    write_general_log,
    write_log,
    clear_logs,
)

__all__ = [
    "resource_path",
    "get_cpu_thread_count",
    "clamp_threads",
    "format_duration",
    "format_bytes",
    "format_time",
    "choose_scale",
    "calculate_files_total_size",
    "predict_encrypted_size",
    "derive_key",
    "safe_print",
    "generate_encrypted_name",
    "get_settings_file",
    "get_default_settings",
    "load_settings",
    "merge_settings",
    "save_settings",
    "get_logs_dir",
    "get_critical_log_file",
    "get_general_log_file",
    "write_critical_log",
    "write_general_log",
    "write_log",
    "clear_logs",
]
