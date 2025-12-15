import logging
import json
import sys
from pathlib import Path
from flask import Flask, request, jsonify
from code_executor import execute_all_subtask_code

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

