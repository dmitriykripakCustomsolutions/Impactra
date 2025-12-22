import ast
import json
import logging
import sys
from pathlib import Path
from flask import Flask, request, jsonify
from cerebras_ai import _call_cerebras_ai_chat

# Add shared module to path for both local and Docker environments
# Try multiple locations to find the shared module
shared_paths = [
    Path(__file__).parent.parent,  # Local development: ../shared
    Path('/app'),  # Docker: /app/shared
]

for path in shared_paths:
    if path.exists():
        sys.path.insert(0, str(path))
        break

from shared import (
    append_error_to_subtasks,
    get_subtasks_for_processing,
    save_subtask_source_code,
    clear_result_artifacts
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def extract_validation_error(validation_result):
    """
    Try to pull the first validation error string from the provided payload.
    Handles dicts and stringified dicts with single quotes.
    """
    if not validation_result:
        return None

    parsed_result = validation_result
    try:
        if isinstance(validation_result, str):
            try:
                parsed_result = json.loads(validation_result)
            except json.JSONDecodeError:
                parsed_result = ast.literal_eval(validation_result)

        if isinstance(parsed_result, dict):
            results = parsed_result.get('results')
            if isinstance(results, list) and results:
                error_msg = results[0].get('error')
                if isinstance(error_msg, str) and error_msg.strip():
                    return error_msg.strip()
    except Exception as e:
        logger.warning(f"Unable to extract validation error: {e}")

    return None


@app.route('/process-task', methods=['POST'])
def process_task():    
    try:
        data = request.get_json(force=True)
    except Exception as e:
        logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({"error": "invalid_json", "details": str(e)}), 400
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    task_id = data.get('taskId')

    validation_result = data.get('validationResult')
    if not task_id:
        return jsonify({"error": "Missing 'taskId' field"}), 400

    try:
        # Load all subtasks from the task folder
        subtasks = get_subtasks_for_processing(task_id)
        
        if not subtasks:
            return jsonify({"error": f"No subtasks found for taskId: {task_id}"}), 404

        validation_error = extract_validation_error(validation_result)
        if validation_error:
            # Clear previous result artifacts for this task to avoid stale files
            clear_result_artifacts(task_id)
            subtasks = append_error_to_subtasks(task_id, validation_error)
        
        results = []
        
        # Process each subtask with Cerebras AI
        for i, subtask in enumerate(subtasks):
            logger.info(f"Processing subtask {i+1}/{len(subtasks)}: {subtask.get('taskName')}")
            
            # Convert subtask dict to JSON string for processing
            subtask_json = json.dumps(subtask)
            
            # Send to Cerebras AI
            result = _call_cerebras_ai_chat(subtask_json)
            
            # Save subtask source code
            save_subtask_source_code(result, task_id, i)
            
            # Wrap result with metadata
            processed_result = {
                "subtaskIndex": i,
                "taskName": subtask.get('taskName'),
                "taskDescription": subtask.get('taskDescription'),
                "completionResult": result
            }
            results.append(processed_result)
            logger.info(f"Completed subtask {i+1}/{len(subtasks)}")

        return jsonify({
            "taskId": task_id,
            "totalSubtasks": len(subtasks),
            "results": results
        }), 200
        
    except FileNotFoundError as e:
        logger.error(f"Task folder not found: {e}")
        return jsonify({"error": "task_not_found", "details": str(e)}), 404
    except Exception as e:
        logger.exception(f"Failed to process task {task_id}")
        return jsonify({"error": "internal_error", "details": str(e)}), 500

@app.route('/receive-test-results', methods=['POST'])
def receive_test_results():    
    # Now it receives test results from the tester:
    # allTestsPassed - boolean and taskId - string
    # We don't need this endpoint so far
    try:
        data = request.get_json(force=True)
    except Exception as e:
        logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({"error": "invalid_json", "details": str(e)}), 400
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    compiled = data.get('compiled', '')
    error = data.get('error', '')
    sourceCode = data.get('sourceCode', '')
    
    logger.info(f"Received code runner result - Compiled: {compiled}, Error: {error}")
    
    return jsonify({"message": "\'receive-test-results\' Endpoint works"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
