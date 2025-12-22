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


def strip_code_fence(s: str) -> str:
    if not s:
        return s
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("\n")[1:]
        if parts and parts[-1].strip().endswith("```"):
            parts = parts[:-1]
        return "\n".join(parts)
    return s


def sanitize_name(name: str) -> str:
    if not name:
        return "unknown"
    sanitized = re.sub(r'[^0-9A-Za-z_]+', '_', name.strip())
    return sanitized or 'unknown'


def sanitize_control_chars_in_json(text: str) -> str:
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


def strip_triple_quotes(s: str) -> str:
    if not s:
        return s
    t = s.strip()
    # Remove triple-quote wrappers if present ("""...""" or '''...''')
    if (t.startswith('"""') and t.endswith('"""')) or (t.startswith("'''") and t.endswith("'''")):
        inner = t[3:-3]
        # remove leading newline if present
        if inner.startswith('\n'):
            inner = inner[1:]
        return inner
    return s


def _convert_triple_quotes_to_json_strings(text: str) -> str:
    # Replace triple-quoted blocks ("""...""" or '''...''') with JSON-compatible
    # double quoted strings with escaped content.
    def _repl(m):
        inner = m.group(2)
        if inner.startswith('\n'):
            inner = inner[1:]
        escaped = inner.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return '"' + escaped + '"'

    return re.sub(r'("""|\'\'\')([\s\S]*?)\1', _repl, text)


def _strip_outer_quotes(s: str) -> str:
    s = s.strip()
    if s and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def try_parse_json_cleaned(cleaned: str):
    """Attempt multiple, ordered strategies to parse JSON-like input produced by LLMs.

    Strategies (in order tried):
    1. Direct json.loads(cleaned)
    2. If parsed is a JSON string, attempt to parse inner JSON or unicode-unescape then parse.
    3. Sanitizing control chars inside string literals and retry loading.
    4. Strip outer quotes, unicode-unescape, convert triple-quoted blocks to JSON strings,
       sanitize control chars, and parse.
    5. Convert triple-quoted blocks in-place and try parsing.
    6. Final fallback: unicode-unescape original and try parsing.
    Returns (parsed, cleaned_used) where cleaned_used is the last transformed string that was parsed.
    """
    # 1) Direct
    try:
        parsed = json.loads(cleaned)
        # 2) If the top-level value is a JSON string containing JSON, try parse inner
        if isinstance(parsed, str):
            # try direct nested
            try:
                nested = json.loads(parsed)
                if isinstance(nested, (dict, list)):
                    return nested, json.dumps(nested)
            except Exception:
                # try unicode unescape then parse
                try:
                    unescaped = parsed.encode('utf-8').decode('unicode_escape')
                    nested = json.loads(unescaped)
                    return nested, unescaped
                except Exception:
                    return parsed, cleaned
        return parsed, cleaned
    except Exception:
        pass

    # 3) Sanitize control chars and try
    try:
        sanitized = sanitize_control_chars_in_json(cleaned)
        parsed = json.loads(sanitized)
        return parsed, sanitized
    except Exception:
        pass

    # 4) Strip outer quotes, unescape, convert triple quotes, sanitize and try
    try:
        s = _strip_outer_quotes(cleaned)
        try:
            s_un = s.encode('utf-8').decode('unicode_escape')
        except Exception:
            s_un = s

        s_conv = _convert_triple_quotes_to_json_strings(s_un)
        s_conv = sanitize_control_chars_in_json(s_conv)

        parsed = json.loads(s_conv)
        return parsed, s_conv
    except Exception:
        pass

    # 5) If there are triple-quoted blocks but no outer wrapping, convert in-place and try
    try:
        s_conv = _convert_triple_quotes_to_json_strings(cleaned)
        s_conv = sanitize_control_chars_in_json(s_conv)
        parsed = json.loads(s_conv)
        return parsed, s_conv
    except Exception:
        pass

    # 6) Final fallback: unicode-unescape original and try
    try:
        unescaped = cleaned.encode('utf-8').decode('unicode_escape')
        parsed = json.loads(unescaped)
        return parsed, unescaped
    except Exception:
        return None, cleaned


def clear_result_artifacts(task_id: str):
    """Remove all files and folders under the task's Result artifacts folder.

    This will leave an empty `Result artifacts` folder in place.
    """
    task_folder = find_task_folder(task_id)
    artifacts_path = os.path.join(task_folder, RESULT_ARTIFACTS_FOLDER)

    if not os.path.exists(artifacts_path):
        logger.info(f"No Result artifacts to clear for taskId {task_id}: {artifacts_path} does not exist")
        return

    # Remove the directory contents safely
    try:
        for entry in os.listdir(artifacts_path):
            full_path = os.path.join(artifacts_path, entry)
            if os.path.isdir(full_path):
                # remove directories recursively
                import shutil

                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
        logger.info(f"Cleared Result artifacts for taskId {task_id}: {artifacts_path}")
    except Exception as e:
        logger.error(f"Failed to clear Result artifacts for taskId {task_id}: {e}")
        raise


def save_subtask_source_code(source_code: str, task_id: str, subtask_index: int):
    try:
        task_folder = find_task_folder(task_id)
        result_artifacts_path = os.path.join(task_folder, RESULT_ARTIFACTS_FOLDER)
        os.makedirs(result_artifacts_path, exist_ok=True)
        logger.info(f"Result artifacts folder ready: {result_artifacts_path}")

        cleaned = strip_code_fence(source_code)
        parsed, cleaned = try_parse_json_cleaned(cleaned)

        saved_paths = []

        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    logger.warning("Skipping non-dict item in parsed subtask source list")
                    continue

                func_name = item.get('function') or item.get('name') or 'unknown'
                func_name = sanitize_name(func_name)

                code_val = item.get('code') or item.get('source') or ''
                # strip triple-quote wrappers commonly used in returned code blocks
                code_val = strip_triple_quotes(code_val)

                completion_order = item.get('completionOrder') or item.get('completion_order')
                try:
                    completion_order = int(completion_order) if completion_order is not None else 0
                except Exception:
                    completion_order = 0

                ext = detect_file_extension(code_val)

                # special-case: items named 'whole_source_code' should be saved with the
                # filename 'Whole source code_subtask_<subtask_index>.<ext>'
                func_normalized = (item.get('function') or item.get('name') or '').strip().lower().replace(' ', '_')
                if func_normalized == 'whole_source_code':
                    base_filename = f"Whole source code_subtask_{subtask_index}_0.{ext}"
                else:
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