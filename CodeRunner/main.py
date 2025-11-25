import logging
import json
import sys
from pathlib import Path
from flask import Flask, request, jsonify
from code_executor import execute_code_safely

# Add shared module to path for both local and Docker environments
shared_paths = [
    Path(__file__).parent.parent,  # Local development: ../shared
    Path('/app'),  # Docker: /app/shared
]

for path in shared_paths:
    if path.exists():
        sys.path.insert(0, str(path))
        break

from shared import find_task_folder

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
RESULT_ARTIFACTS_FOLDER = "result artifacts"

def get_source_code_files(task_id: str):
    """
    Find and read all source code files from the task's result artifacts folder.
    Returns a list of tuples: (filename, source_code)
    """
    try:
        task_folder = find_task_folder(task_id)
        result_artifacts_path = Path(task_folder) / RESULT_ARTIFACTS_FOLDER
        
        if not result_artifacts_path.exists():
            logger.warning(f"Result artifacts folder not found: {result_artifacts_path}")
            return []
        
        # Find all source code files matching pattern: Source Code_subtask_<number>.<extension>
        source_files = sorted(
            result_artifacts_path.glob("Source Code_subtask_*"),
            key=lambda f: extract_order_from_filename(f.name)
        )
        
        if not source_files:
            logger.warning(f"No source code files found in: {result_artifacts_path}")
            return []
        
        logger.info(f"Found {len(source_files)} source code files: {[f.name for f in source_files]}")
        
        # Read all files
        files_with_content = []
        for file_path in source_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    files_with_content.append((file_path.name, content))
                    logger.info(f"Loaded source code from: {file_path.name}")
            except Exception as e:
                logger.error(f"Failed to read file {file_path.name}: {e}")
                raise
        
        return files_with_content
        
    except FileNotFoundError as e:
        logger.error(f"Task folder not found for taskId {task_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error retrieving source code files for taskId {task_id}: {e}")
        raise

def extract_order_from_filename(filename: str) -> int:
    """
    Extract the order number from filename like: Source Code_subtask_0.py
    """
    import re
    match = re.search(r'_(\d+)\.', filename)
    if match:
        return int(match.group(1))
    return float('inf')

def execute_all_subtask_code(task_id: str):
    """
    Execute all source code files for a task and return results.
    """
    try:
        # Get all source code files
        source_files = get_source_code_files(task_id)

        # Determine the task folder and result artifacts path so we can write per-subtask results
        task_folder = find_task_folder(task_id)
        result_artifacts_path = Path(task_folder) / RESULT_ARTIFACTS_FOLDER
        
        if not source_files:
            return {
                "taskId": task_id,
                "results": [],
                "status": "no_code_files_found"
            }
        
        # Execute each file and collect results
        execution_results = []
        for filename, source_code in source_files:
            logger.info(f"Executing {filename}...")
            try:
                result = execute_code_safely(source_code)
                execution_results.append({
                    "subtask": filename,
                    "compiled": result.get("compiled", False),
                    "output": result.get("output", ""),
                    "error": result.get("error", ""),
                    "sourceCode": result.get("sourceCode", "")
                })
                # Attempt to derive subtask index from filename; fall back to enumerating
                try:
                    subtask_index = extract_order_from_filename(filename)
                    if not isinstance(subtask_index, int):
                        raise ValueError
                except Exception:
                    # fallback: use current length of execution_results - 1 as index
                    subtask_index = len(execution_results) - 1

                # Ensure result artifacts folder exists
                try:
                    result_artifacts_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.warning(f"Could not create result artifacts folder {result_artifacts_path}: {e}")

                # Write the per-subtask result to JSON file
                try:
                    result_item = execution_results[-1]
                    output_file = result_artifacts_path / f"run result_subtask_{subtask_index}.json"
                    with open(output_file, 'w', encoding='utf-8') as out_f:
                        json.dump(result_item, out_f, ensure_ascii=False, indent=2)
                    logger.info(f"Saved run result to {output_file}")
                except Exception as e:
                    logger.error(f"Failed to write run result for {filename}: {e}")
                logger.info(f"✓ Completed execution of {filename}")
            except Exception as e:
                logger.error(f"Failed to execute {filename}: {e}")
                execution_results.append({
                    "subtask": filename,
                    "compiled": False,
                    "output": "",
                    "error": str(e),
                    "sourceCode": source_code
                })
        
        return {
            "taskId": task_id,
            "results": execution_results,
            "status": "success",
            "totalSubtasks": len(source_files),
            "successfulExecutions": sum(1 for r in execution_results if r["compiled"])
        }
        
    except Exception as e:
        logger.error(f"Error executing subtasks for taskId {task_id}: {e}")
        return {
            "taskId": task_id,
            "results": [],
            "status": "error",
            "error": str(e)
        }

@app.route('/run-code', methods=['POST'])
def run_code():
    try:
        data = request.get_json()
        task_id = data.get('taskId')
        
        if not task_id:
            logger.warning("Request missing 'taskId' field")
            return jsonify({
                "error": "Invalid request. 'taskId' field is required.",
                "status": "error"
            }), 400
        
        logger.info(f"Processing run-code request for taskId: {task_id}")
        result = execute_all_subtask_code(task_id)
        
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error processing run-code request: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "status": "error",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)

