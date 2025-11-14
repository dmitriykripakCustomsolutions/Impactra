import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from cerebras_ai import _cerebras_ai_generate_folder_name

logger = logging.getLogger(__name__)

# Docker volume mount path for persistent storage
TASKS_VOLUME_PATH = "/data/tasks"


def ensure_tasks_folder() -> str:
    tasks_path = Path(TASKS_VOLUME_PATH)
    try:
        tasks_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Tasks folder ensured at: {tasks_path}")
        return str(tasks_path)
    except Exception as e:
        logger.error(f"Failed to create tasks folder: {e}")
        raise


def generate_task_folder_name_from_description(original: str) -> str:
    try:
        # Create a prompt to generate a short, concise folder name (max 3-5 words)
        prompt = (
            f"Given the following task description, generate a SHORT folder name (3-5 words max, lowercase, no special chars except underscores). "
            f"Use only letters, numbers, and underscores. No spaces. Example: 'build_api_endpoint' or 'fix_auth_bug'.\n\n"
            f"Task: {original}"
        )
        
        # Call Cerebras AI to generate the folder name
        ai_folder_name = _cerebras_ai_generate_folder_name(prompt, max_tokens=50)
        
        # Clean the response - remove any extra whitespace and special characters
        ai_folder_name = ai_folder_name.strip().lower()
        ai_folder_name = "".join(c for c in ai_folder_name if c.isalnum() or c == '_')
        
        # Ensure it's not empty and not too long
        if not ai_folder_name:
            ai_folder_name = "task"
        if len(ai_folder_name) > 50:
            ai_folder_name = ai_folder_name[:50]
        
        # Combine timestamp with AI-generated name
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"{now}_{ai_folder_name}"
        
        logger.info(f"Generated AI-based folder name: {folder_name}")
        return folder_name
    
    except Exception as e:
        logger.warning(f"Failed to generate AI-based folder name, falling back to timestamp: {e}")
        # Fallback to just timestamp if AI call fails
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return now


def save_original_requirements(folder_path: str, original_text: str) -> None:
    """
    Save the original task requirements to a text file.
    
    Args:
        folder_path: Path to the task-specific folder
        original_text: The raw original task requirements text
        
    Raises:
        Exception: If file write fails
    """
    try:
        file_path = Path(folder_path) / "Original task requirements.txt"
        file_path.write_text(original_text, encoding="utf-8")
        logger.info(f"Saved original requirements to: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save original requirements: {e}")
        raise


def save_subtasks(folder_path: str, tasks_data: Any) -> None:
    """
    Save individual subtasks as JSON files.
    Each task from the tasks array is saved as a separate JSON file named after taskName.
    
    Args:
        folder_path: Path to the task-specific folder
        tasks_data: The tasks data (could be string or list)
        
    Raises:
        Exception: If parsing or file write fails
    """
    try:
        # Parse tasks_data if it's a string
        if isinstance(tasks_data, str):
            tasks_list = json.loads(tasks_data)
        else:
            tasks_list = tasks_data
        
        # Ensure tasks_list is a list
        if not isinstance(tasks_list, list):
            logger.warning(f"Tasks data is not a list. Type: {type(tasks_list)}")
            tasks_list = [tasks_list]
        
        # Save each task as a JSON file
        for idx, task in enumerate(tasks_list):
            if isinstance(task, dict):
                task_name = task.get("taskName", f"task_{idx}")
                # Sanitize filename
                safe_task_name = "".join(c for c in task_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
                if not safe_task_name:
                    safe_task_name = f"task_{idx}"
                
                file_path = Path(folder_path) / f"{safe_task_name}.json"
                file_path.write_text(json.dumps(task, indent=2), encoding="utf-8")
                logger.info(f"Saved task to: {file_path}")
            else:
                logger.warning(f"Task at index {idx} is not a dict: {task}")
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tasks JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to save subtasks: {e}")
        raise


def save_task_results(original: str, tasks_result: Any, tasks_id: Any) -> Dict[str, Any]:
    try:
        # Ensure tasks folder exists
        tasks_base = ensure_tasks_folder()
        
        # Generate AI-based folder name from original task description
        folder_name = generate_task_folder_name_from_description(original)
        task_folder_path = Path(tasks_base) / f'{tasks_id}_{folder_name}'
        task_folder_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created task folder: {task_folder_path}")
        
        # Save original requirements
        save_original_requirements(str(task_folder_path), original)
        
        # Save subtasks
        save_subtasks(str(task_folder_path), tasks_result)
        
        return {
            "status": "success",
            "folder_path": str(task_folder_path),
            "message": f"Task results saved to {task_folder_path}"
        }
    
    except Exception as e:
        logger.error(f"Failed to save task results: {e}")
        return {
            "status": "error",
            "message": f"Failed to save task results: {str(e)}"
        }
