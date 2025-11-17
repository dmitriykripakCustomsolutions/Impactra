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
RESULT_ARTIFACTS_FOLDER = "result artifacts"

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
        # Find the task folder
        task_folder = find_task_folder(task_id)
        
        # Create result artifacts subfolder if it doesn't exist
        result_artifacts_path = os.path.join(task_folder, RESULT_ARTIFACTS_FOLDER)
        os.makedirs(result_artifacts_path, exist_ok=True)
        logger.info(f"Result artifacts folder ready: {result_artifacts_path}")
        
        # Detect file extension from source code
        file_extension = detect_file_extension(source_code)
        
        # Create filename: Source Code_subtask_<index>.<extension>
        filename = f"Source Code_subtask_{subtask_index}.{file_extension}"
        file_path = os.path.join(result_artifacts_path, filename)
        
        # Write the source code to file
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
