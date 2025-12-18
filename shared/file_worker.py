import os
import json
import logging
import re
import time
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Path to the data volume
DATA_BASE_PATH = "/data/tasks"

# Result artifacts folder name
RESULT_ARTIFACTS_FOLDER = "Result artifacts"

# Language detection patterns - maps common keywords/patterns to file extensions
LANGUAGE_PATTERNS = {
    r'\bimport\s+\w+\b|\bfrom\s+\w+\s+import\b|\bdef\s+\w+\s*\(|\bclass\s+\w+|\bif\s+__name__\s*==': 'py',
    r'\busing\s+\w+\s*;|\bnamespace\s+\w+|\bpublic\s+class\b|\bpublic\s+static\s+void\b': 'cs',
    r'\bfunction\s+\w+|\bconst\s+\w+\s*=|\blet\s+\w+\s*=|\bvar\s+\w+\s*=|\bconsole\.log\(|\bexport\s+(default|class|function)': 'js',
    r'\bfn\s+\w+\s*\(|\blet\s+\w+\s*=|\bmut\s+\w+|\bcrate::|\bstd::': 'rs',
    r'\bfunc\s+\w+\s*\(|\bvar\s+\w+\s+\w+|\bpackage\s+\w+|\bimport\s+"\w+\"': 'go',
    r'\bpackage\s+\w+\s*;|\bpublic\s+class\b|\bpublic\s+static\b|\bimport\s+\w+\.\w+\s*;': 'java',
    r'\bdef\s+\w+|\bclass\s+\w+|\brequire\s+["\']|\bRuby\s+version': 'rb',
    r'\becho\s+|\bif\s+\[\[|\bwhile\s+\[\[|\bfor\s+\w+\s+in': 'sh',
    r'--.*comment|local\s+\w+|function\s+\w+': 'lua',
    r'\$\w+|\becho\b|\bforeach\b|\bfunction\b': 'ps1',
}


def find_task_folder(task_id: str, max_attempts: int = 5, base_delay: float = 1.0) -> str:
    attempt = 0
    last_exception = None
    
    while attempt < max_attempts:
        attempt += 1
        attempt_start_time = time.time()
        
        logger.info(f"Attempt {attempt}/{max_attempts} to find task folder for taskId: {task_id}")
        
        try:
            if not os.path.exists(DATA_BASE_PATH):
                raise FileNotFoundError(f"Data path does not exist: {DATA_BASE_PATH}")
            
            # List all contents in DATA_BASE_PATH for debugging
            all_items = os.listdir(DATA_BASE_PATH)
            logger.debug(f"Contents of {DATA_BASE_PATH}: {all_items}")
            
            for folder_name in all_items:
                folder_path = os.path.join(DATA_BASE_PATH, folder_name)
                logger.debug(f"Checking: {folder_name} (full path: {folder_path}, is_dir: {os.path.isdir(folder_path)})")
                
                if task_id in folder_name:
                    if os.path.isdir(folder_path):
                        attempt_duration = time.time() - attempt_start_time
                        logger.info(f"✓ Found task folder on attempt {attempt}/{max_attempts}: {folder_path} (took {attempt_duration:.2f}s)")
                        return folder_path
                    else:
                        logger.warning(f"Found matching name '{folder_name}' but it's not a directory")
            
            # Folder not found on this attempt
            attempt_duration = time.time() - attempt_start_time
            logger.warning(f"Task folder not found in attempt {attempt}/{max_attempts} (took {attempt_duration:.2f}s). taskId: {task_id}")
            
            # If not the last attempt, calculate backoff and wait
            if attempt < max_attempts:
                backoff_delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff: 1s, 2s, 4s, 8s
                logger.info(f"Waiting {backoff_delay:.2f}s before retry (exponential backoff factor: 2^{attempt - 1})")
                time.sleep(backoff_delay)
            
        except FileNotFoundError as e:
            last_exception = e
            attempt_duration = time.time() - attempt_start_time
            logger.error(f"FileNotFoundError on attempt {attempt}/{max_attempts} (took {attempt_duration:.2f}s): {e}")
            
            if attempt < max_attempts:
                backoff_delay = base_delay * (2 ** (attempt - 1))
                logger.info(f"Waiting {backoff_delay:.2f}s before retry (exponential backoff factor: 2^{attempt - 1})")
                time.sleep(backoff_delay)
        except Exception as e:
            last_exception = e
            attempt_duration = time.time() - attempt_start_time
            logger.error(f"Unexpected error on attempt {attempt}/{max_attempts} (took {attempt_duration:.2f}s): {e}")
            
            if attempt < max_attempts:
                backoff_delay = base_delay * (2 ** (attempt - 1))
                logger.info(f"Waiting {backoff_delay:.2f}s before retry (exponential backoff factor: 2^{attempt - 1})")
                time.sleep(backoff_delay)
    
    # All attempts exhausted
    error_msg = f"No folder found containing taskId: {task_id} after {max_attempts} attempts"
    logger.error(f"✗ Failed to find task folder after {max_attempts} attempts for taskId: {task_id}")
    if last_exception:
        logger.error(f"Last exception: {last_exception}")
    raise FileNotFoundError(error_msg)


def extract_order_number(filename: str) -> int:
    """
    Extract the order number suffix from a filename.
    Assumes format like: subtask_1.json, subtask_2.json, etc.
    """
    match = re.search(r'_(\d+)\.json$', filename)
    if match:
        return int(match.group(1))
    return float('inf')


def read_subtasks(task_id: str) -> List[Dict[str, Any]]:
    task_folder = find_task_folder(task_id)
    subtasks = []
    
    try:
        # Find all JSON files in the task folder
        json_files = [
            f for f in os.listdir(task_folder)
            if f.endswith('.json')
        ]
        
        if not json_files:
            logger.warning(f"No JSON files found in task folder: {task_folder}")
            return subtasks
        
        # Sort files by order number
        json_files.sort(key=extract_order_number)
        logger.info(f"Found {len(json_files)} subtask files in order: {json_files}")
        
        # Read each file in order
        for filename in json_files:
            file_path = os.path.join(task_folder, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Validate required fields
                    if 'taskName' not in data or 'taskDescription' not in data:
                        logger.warning(
                            f"Subtask file missing required fields: {filename}. "
                            f"Expected 'taskName' and 'taskDescription'"
                        )
                        continue
                    
                    subtasks.append(data)
                    logger.info(f"Loaded subtask from {filename}: {data.get('taskName')}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON file {filename}: {e}")
                raise
            except Exception as e:
                logger.error(f"Error reading file {filename}: {e}")
                raise
        
        logger.info(f"Successfully loaded {len(subtasks)} subtasks for task {task_id}")
        return subtasks
        
    except Exception as e:
        logger.error(f"Error reading subtasks for task {task_id}: {e}")
        raise


def get_subtasks_for_processing(task_id: str) -> List[Dict[str, Any]]:
    try:
        subtasks = read_subtasks(task_id)
        return subtasks
    except FileNotFoundError as e:
        logger.error(f"Task folder not found for taskId {task_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving subtasks for taskId {task_id}: {e}")
        raise


def append_error_to_subtasks(task_id: str, error_message: str) -> List[Dict[str, Any]]:
    """
    Append a validation error hint to every subtask description and persist changes.
    Returns the updated subtask payloads.
    """
    if not error_message:
        logger.info("Empty error message supplied, skipping subtask updates")
        return read_subtasks(task_id)

    task_folder = find_task_folder(task_id)
    json_files = [
        f for f in os.listdir(task_folder)
        if f.endswith('.json')
    ]

    if not json_files:
        logger.warning(f"No JSON subtask files found for taskId {task_id}")
        return []

    json_files.sort(key=extract_order_number)
    updated_subtasks: List[Dict[str, Any]] = []
    error_suffix = f"Consider the possible error: {error_message.strip()}"

    for filename in json_files:
        file_path = os.path.join(task_folder, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        description = data.get('taskDescription')
        if isinstance(description, str):
            if error_suffix not in description:
                spacer = "" if description.endswith((" ", "\n")) else " "
                data['taskDescription'] = f"{description}{spacer}{error_suffix}"
        else:
            logger.warning(
                f"Subtask {filename} missing string taskDescription; skipping append"
            )

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        updated_subtasks.append(data)
        logger.info(f"Updated taskDescription with validation error in {filename}")

    return updated_subtasks


def detect_file_extension(source_code: str) -> str:
    """
    Detect the programming language from source code content.
    
    Args:
        source_code: The source code content to analyze
        
    Returns:
        str: File extension (e.g., 'py', 'js', 'cs') or 'txt' if unknown
    """
    if not source_code:
        logger.warning("Empty source code provided, defaulting to 'txt'")
        return 'txt'
    
    # Normalize whitespace
    code = source_code.strip()
    
    # Check patterns in order of specificity
    for pattern, extension in LANGUAGE_PATTERNS.items():
        if re.search(pattern, code, re.MULTILINE | re.IGNORECASE):
            logger.debug(f"Detected language extension: {extension}")
            return extension
    
    # Try to detect by common file headers or shebang
    if code.startswith('#!/usr/bin/env python'):
        return 'py'
    elif code.startswith('#!/bin/bash'):
        return 'sh'
    elif code.startswith('#!/usr/bin/env node'):
        return 'js'
    
    # Check for common language-specific imports/declarations at the beginning
    lines = code.split('\n')[:10]  # Check first 10 lines
    code_start = '\n'.join(lines)
    
    if re.search(r'^\s*import\s+\w+|^\s*from\s+\w+\s+import', code_start, re.MULTILINE):
        return 'py'
    elif re.search(r'^\s*using\s+\w+|^\s*namespace\s+\w+', code_start, re.MULTILINE):
        return 'cs'
    elif re.search(r'^\s*(import|export|const|let|var|function|class)', code_start, re.MULTILINE):
        return 'js'
    
    logger.warning(f"Could not detect language from source code, defaulting to 'txt'")
    return 'txt'


def save_subtask_source_code(source_code: str, task_id: str, subtask_index: int) -> str:
    try:
        task_folder = find_task_folder(task_id)
        result_artifacts_path = os.path.join(task_folder, RESULT_ARTIFACTS_FOLDER)
        os.makedirs(result_artifacts_path, exist_ok=True)
        logger.info(f"Result artifacts folder ready: {result_artifacts_path}")

        def _strip_code_fence(s: str) -> str:
            if not s:
                return s
            s = s.strip()
            if s.startswith("```"):
                parts = s.split("\n")
                parts = parts[1:]
                if parts and parts[-1].strip().endswith("```"):
                    parts = parts[:-1]
                return "\n".join(parts)
            return s

        def _sanitize_name(name: str) -> str:
            if not name:
                return "unknown"
            sanitized = re.sub(r'[^0-9A-Za-z_]+', '_', name.strip())
            return sanitized or 'unknown'

        cleaned = _strip_code_fence(source_code)

        parsed = None

        # Robust JSON parsing:
        # - Handle normal JSON arrays/objects
        # - Handle JSON that is double-encoded (a JSON string containing JSON)
        # - Handle escaped newlines and other escape sequences (e.g. "\n") by unescaping
        try:
            parsed = json.loads(cleaned)

            # If the value is a JSON-encoded string, try to parse the inner value.
            if isinstance(parsed, str):
                try:
                    nested = json.loads(parsed)
                    parsed = nested
                    # If nested was parsed successfully, update the cleaned text
                    if isinstance(nested, (dict, list)):
                        cleaned = json.dumps(nested)
                    else:
                        cleaned = str(nested)
                except Exception:
                    # Try unescaping common escape sequences and parse again
                    try:
                        unescaped = parsed.encode('utf-8').decode('unicode_escape')
                        parsed = json.loads(unescaped)
                        cleaned = unescaped
                    except Exception:
                        # leave parsed as string if we can't parse deeper
                        pass

        except Exception as ex:
            # First attempt failed — try to recover.
            # Common issue: JSON contains unescaped literal newlines or other control
            # characters inside quoted strings (Invalid control character). Sanitize
            # such control chars inside strings by escaping them (\n, \r, \t)
            def _sanitize_control_chars_in_json(text: str) -> str:
                out_chars = []
                in_string = False
                esc = False

                for ch in text:
                    if ch == '"' and not esc:
                        out_chars.append(ch)
                        in_string = not in_string
                        esc = False
                        continue

                    if ch == '\\' and not esc:
                        out_chars.append(ch)
                        esc = True
                        continue

                    if esc:
                        out_chars.append(ch)
                        esc = False
                        continue

                    if in_string:
                        if ch == '\n':
                            out_chars.append('\\n')
                            continue
                        if ch == '\r':
                            out_chars.append('\\r')
                            continue
                        if ch == '\t':
                            out_chars.append('\\t')
                            continue
                        if ord(ch) < 0x20:
                            out_chars.append('\\u%04x' % ord(ch))
                            continue

                    out_chars.append(ch)

                return ''.join(out_chars)

            parsed = None
            try:
                sanitized = _sanitize_control_chars_in_json(cleaned)
                parsed = json.loads(sanitized)
                cleaned = sanitized
            except Exception:
                # Fallback strategies: try unicode_escape unescape, strip surrounding quotes
                try:
                    unescaped = cleaned.encode('utf-8').decode('unicode_escape')
                    parsed = json.loads(unescaped)
                    cleaned = unescaped
                except Exception:
                    stripped = None
                    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
                        stripped = cleaned[1:-1]

                    if stripped is not None:
                        try:
                            parsed = json.loads(stripped)
                            cleaned = stripped
                        except Exception:
                            try:
                                unescaped2 = stripped.encode('utf-8').decode('unicode_escape')
                                parsed = json.loads(unescaped2)
                                cleaned = unescaped2
                            except Exception:
                                parsed = None
                    else:
                        parsed = None

            if parsed is None:
                logger.warning(f"Failed to parse subtask source as JSON: {ex}")

        saved_paths = []

        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    logger.warning("Skipping non-dict item in parsed subtask source list")
                    continue

                func_name = item.get('function') or item.get('name') or 'unknown'
                func_name = _sanitize_name(func_name)

                code_val = item.get('code') or item.get('source') or ''

                completion_order = item.get('completionOrder') or item.get('completion_order')
                try:
                    completion_order = int(completion_order) if completion_order is not None else 0
                except Exception:
                    completion_order = 0

                ext = detect_file_extension(code_val)
                base_filename = f"Source {func_name}_subtask_{subtask_index}_{completion_order}.{ext}"
                file_path = os.path.join(result_artifacts_path, base_filename)

                i = 1
                while os.path.exists(file_path):
                    file_path = os.path.join(result_artifacts_path, f"Source {func_name}_subtask_{subtask_index}_{completion_order}_{i}.{ext}")
                    i += 1

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code_val)

                saved_paths.append(file_path)
                logger.info(f"Saved subtask source for function '{func_name}' to: {file_path}")

            return saved_paths

        # Fallback: save whole body as a single file
        file_extension = detect_file_extension(cleaned)
        filename = f"Source Code_subtask_{subtask_index}.{file_extension}"
        file_path = os.path.join(result_artifacts_path, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(source_code)

        logger.info(f"Successfully saved subtask source code to: {file_path}")
        return file_path

    except FileNotFoundError as e:
        logger.error(f"Task folder not found for taskId {task_id}: {e}")
        raise
    except IOError as e:
        logger.error(f"Failed to write source code file: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error saving source code for taskId {task_id}, subtask {subtask_index}: {e}")
        raise
