import logging
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/process-task', methods=['POST'])
def process_task():    
    try:
        data = request.get_json(force=True)
        raw = data.get('tasks') or data.get('text') or ''
    except Exception as e:
        app.logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({"error": "invalid_json", "details": str(e)}), 400
    
    if not raw:
        return jsonify({"error": "No 'message' provided"}), 400

    try:
        result = _call_cerebras_ai_chat(raw)
        return jsonify({"original": raw, "tasks": result}), 200
    except Exception as e:
        app.logger.exception("Failed to analyze message")
        return jsonify({"error": "internal_error", "details": str(e)}), 500

@app.route('/receive-code-runner-result', methods=['POST'])
def receive_code_runner_result():    
    # if request.is_json:
    #     data = request.get_json()
    #     message = data.get('message', '')
    # else:
    #     # If form-urlencoded
    #     message = request.form.get('message', '')
    # app.logger.info(f"A message received: {message}")
    # return jsonify({"status": "ok", "received": message}), 200
    return jsonify({"message": "\'receive-code-runner-result\' Endpoint works"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
