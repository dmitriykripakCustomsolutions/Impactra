"""
Shared library module for Impactra services.

This module provides common utilities used across multiple services:
- BusinessAnalyst
- Programmer
- CodeRunner
- Tester
"""

from .file_worker import (
    find_task_folder,
    extract_order_number,
    read_subtasks,
    get_subtasks_for_processing,
    append_error_to_subtasks,
    detect_file_extension,
    save_subtask_source_code,
    clear_result_artifacts,
    DATA_BASE_PATH,
    RESULT_ARTIFACTS_FOLDER,
    LANGUAGE_PATTERNS,
)

__all__ = [
    "find_task_folder",
    "extract_order_number",
    "read_subtasks",
    "get_subtasks_for_processing",
    "append_error_to_subtasks",
    "detect_file_extension",
    "save_subtask_source_code",
    "clear_result_artifacts",
    "DATA_BASE_PATH",
    "RESULT_ARTIFACTS_FOLDER",
    "LANGUAGE_PATTERNS",
]
