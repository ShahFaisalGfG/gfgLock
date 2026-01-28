# utils/__init__.py
# Public API for utils module - exports helper functions and utilities

from utils.gfg_helpers import (
    resource_path,
    get_cpu_thread_count,
    clamp_threads,
    format_duration,
    derive_key,
    safe_print,
    get_settings_file,
    get_default_settings,
    load_settings,
    merge_settings,
    save_settings,
    get_logs_dir,
    get_critical_log_file,
    get_general_log_file,
    write_critical_log,
    write_general_log,
    write_log,
    clear_logs,
    predict_encrypted_size,
    calculate_files_total_size,
    format_bytes,
    format_time,
    choose_scale,
)

from utils.theme_manager import apply_theme

__all__ = [
    # gfg_helpers exports
    'resource_path',
    'get_cpu_thread_count',
    'clamp_threads',
    'format_duration',
    'derive_key',
    'safe_print',
    'get_settings_file',
    'get_default_settings',
    'load_settings',
    'merge_settings',
    'save_settings',
    'get_logs_dir',
    'get_critical_log_file',
    'get_general_log_file',
    'write_critical_log',
    'write_general_log',
    'write_log',
    'clear_logs',
    'predict_encrypted_size',
    'apply_theme',
    'calculate_files_total_size',
    'format_bytes',
    'format_time',
    'choose_scale',
]
