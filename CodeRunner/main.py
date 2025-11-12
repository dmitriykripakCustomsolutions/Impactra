import logging
import json

from flask import Flask, request, jsonify
from code_executor import execute_code_safely


app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/run-code', methods=['POST'])
def receive_message():
    try:
        data = request.get_json()
        sourceCode = data.get('sourceCode', '')
        if not sourceCode:
            return jsonify({
                "error": "Invalid request. 'completionResult' field is required.",
                "compiled": False
            }), 400

        result = execute_code_safely(sourceCode)
        return jsonify({"result": result})

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "compiled": False
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
