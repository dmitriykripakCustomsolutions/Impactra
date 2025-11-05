import logging

from flask import Flask, request, jsonify
from cerebras_ai import _call_cerebras_ai_chat
from open_ai import _call_openai_chat


app = Flask(__name__)



@app.route('/receive-message', methods=['POST'])
def receive_message():
    try:
        data = request.get_json(force=True)
        raw = data.get('message') or data.get('text') or ''
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


@app.route('/receive-task-completion-result', methods=['POST'])
def receive_task_completion_result():
    # TODO: hook for receiving results from downstream agents; kept minimal to not break current behavior
    if request.is_json:
        data = request.get_json()
        return jsonify({"status": "received", "data": data}), 200
    else:
        return jsonify({"status": "ok", "message": "No JSON payload provided"}), 200


if __name__ == '__main__':
    # Enable basic logging
    logging.basicConfig(level=logging.INFO)
    # _call_openai_chat(prompt="Hello, world!")
    # _call_cerebras_ai_chat(prompt="Write a simple array insertion sort algorithm in python.")
    app.run(host='0.0.0.0', port=5000)
