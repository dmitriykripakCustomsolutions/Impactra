import json
from flask import Flask, request, jsonify
from cerebras_ai import _call_cerebras_ai_chat

app = Flask(__name__)

@app.route('/process-task', methods=['POST'])
def process_task():    
    try:
        data = request.get_json(force=True)
    except Exception as e:
        app.logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({"error": "invalid_json", "details": str(e)}), 400
    
    if not data:
        return jsonify({"error": "No 'message' provided"}), 400

    try:
        for i in range(len(data)):
            print(f"Index {i}: {data[i]}")
            taskJsonFormatted = json.dumps(data[i])
            result = _call_cerebras_ai_chat(taskJsonFormatted)
            response = json.dumps({"sourceCode": result})

        return jsonify({"task": taskJsonFormatted, "completionResult": response}), 200
    except Exception as e:
        app.logger.exception("Failed to analyze message")
        return jsonify({"error": "internal_error", "details": str(e)}), 500

@app.route('/receive-code-runner-result', methods=['POST'])
def receive_code_runner_result():    
    try:
        data = request.get_json(force=True)
    except Exception as e:
        app.logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({"error": "invalid_json", "details": str(e)}), 400
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    compiled = data.get('compiled', '')
    error = data.get('error', '')
    sourceCode = data.get('sourceCode', '')
    
    return jsonify({"message": "\'receive-code-runner-result\' Endpoint works"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
