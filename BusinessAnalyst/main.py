import logging
import uuid
from pathlib import Path

from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

from cerebras_ai import _call_cerebras_ai_chat
from open_ai import _call_openai_chat
from task_storage import save_task_results


app = Flask(__name__)

@app.route('/receive-message', methods=['POST'])
def receive_message():
    try:
        # Support both JSON and form/multipart requests
        if request.is_json:
            data = request.get_json(force=True)
            raw = data.get('message') or data.get('text') or ''
            uploaded_file = None
        else:
            # form or multipart: message can be in form fields, file(s) in request.files
            raw = request.form.get('message') or request.form.get('text') or ''
            # prefer field name 'attachment', fallback to first file
            uploaded_file = request.files.get('attachment') or (next(iter(request.files.values())) if request.files else None)
    except Exception as e:
        app.logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({"error": "invalid_json", "details": str(e)}), 400
    
    if not raw:
        return jsonify({"error": "No 'message' provided"}), 400

    try:
        result = _call_cerebras_ai_chat(raw)
        task_id = str(uuid.uuid4())

        # Save task creation results to volume
        try:
            storage_result = save_task_results(original=raw, tasks_result=result, task_id=task_id)
            app.logger.info(f"Task storage: {storage_result}")
        except Exception as storage_error:
            app.logger.warning(f"Failed to save task results to volume: {storage_error}")
            storage_result = {"status": "error", "message": str(storage_error)}

        # If an uploaded file is present and storage succeeded, save the file into the same folder
        file_saved = None
        try:
            if uploaded_file and storage_result.get("status") == "success":
                folder_path = storage_result.get("folder_path")
                if folder_path:
                    filename = secure_filename(uploaded_file.filename) or "uploaded_file"
                    target = Path(folder_path) / filename
                    uploaded_file.save(str(target))
                    app.logger.info(f"Saved uploaded file to: {target}")
                    file_saved = str(target)
                else:
                    app.logger.warning("Storage reported success but no folder_path returned; uploaded file not saved")
        except Exception as save_file_error:
            app.logger.warning(f"Failed to save uploaded file: {save_file_error}")

        response_payload = {"taskId": task_id}
        if storage_result:
            response_payload["storage"] = storage_result
        if file_saved:
            response_payload["saved_file"] = file_saved

        return jsonify(response_payload), 200
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
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5000)
