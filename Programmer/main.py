import json
import logging
from flask import Flask, request, jsonify
from cerebras_ai import _call_cerebras_ai_chat
from file_worker import get_subtasks_for_processing, save_subtask_source_code

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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
    if not task_id:
        return jsonify({"error": "Missing 'taskId' field"}), 400

    try:
        # Load all subtasks from the task folder
        subtasks = get_subtasks_for_processing(task_id)
        
        if not subtasks:
            return jsonify({"error": f"No subtasks found for taskId: {task_id}"}), 404
        
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

@app.route('/receive-code-runner-result', methods=['POST'])
def receive_code_runner_result():    
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
    
    return jsonify({"message": "\'receive-code-runner-result\' Endpoint works"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
