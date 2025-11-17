import os
import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Path to the data volume
DATA_BASE_PATH = "/data/tasks"


def find_task_folder(task_id: str) -> str:
    """
    Find the folder that contains the taskId in its name.
    
    Args:
        task_id: The task ID to search for
        
    Returns:
        str: Full path to the task folder
        
    Raises:
        FileNotFoundError: If no folder containing the taskId is found
    """
    if not os.path.exists(DATA_BASE_PATH):
        raise FileNotFoundError(f"Data path does not exist: {DATA_BASE_PATH}")
    
    try:
        for folder_name in os.listdir(DATA_BASE_PATH):
            if task_id in folder_name:
                folder_path = os.path.join(DATA_BASE_PATH, folder_name)
                if os.path.isdir(folder_path):
                    logger.info(f"Found task folder: {folder_path}")
                    return folder_path
    except Exception as e:
        logger.error(f"Error searching for task folder: {e}")
        raise
    
    raise FileNotFoundError(f"No folder found containing taskId: {task_id}")


def extract_order_number(filename: str) -> int:
    """
    Extract the order number suffix from a filename.
    Assumes format like: subtask_1.json, subtask_2.json, etc.
    
    Args:
        filename: The filename to extract order from
        
    Returns:
        int: The order number, or float('inf') if no number found (sorts to end)
    """
    match = re.search(r'_(\d+)\.json$', filename)
    if match:
        return int(match.group(1))
    return float('inf')


def read_subtasks(task_id: str) -> List[Dict[str, Any]]:
    """
    Read all subtask JSON files from the task folder in correct order.
    
    Args:
        task_id: The task ID to read subtasks for
        
    Returns:
        List[Dict]: List of subtask dictionaries containing 'taskName' and 'taskDescription'
        
    Raises:
        FileNotFoundError: If task folder not found
        json.JSONDecodeError: If JSON parsing fails
    """
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
    """
    Convenience function to get all subtasks ready for processing.
    Wraps read_subtasks with additional error handling.
    
    Args:
        task_id: The task ID to process
        
    Returns:
        List[Dict]: List of subtasks
    """
    try:
        subtasks = read_subtasks(task_id)
        return subtasks
    except FileNotFoundError as e:
        logger.error(f"Task folder not found for taskId {task_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving subtasks for taskId {task_id}: {e}")
        raise
