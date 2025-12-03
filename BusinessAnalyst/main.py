import logging
import uuid
import json
import re
import base64
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
        raw = (
            request.form.get('message')
            or request.form.get('text')
            or request.values.get('message')
            or request.values.get('text')
            or ''
        )

        # Collect all uploaded files (support multiple files). Accept common field names.
        uploaded_files = []
        if request.files:
            # prefer explicit names first
            for name in ('attachment', 'file', 'upload'):
                f = request.files.get(name)
                if f:
                    uploaded_files.append(f)
            # then add any remaining files
            for f in request.files.values():
                if f not in uploaded_files:
                    uploaded_files.append(f)
    except Exception as e:
        app.logger.error(f"Failed to parse multipart request: {e}")
        return jsonify({"error": "invalid_request", "details": str(e)}), 400

    if not raw:
        return jsonify({"error": "No 'message' provided"}), 400

    try:
        # Call AI to produce tasks
        result = _call_cerebras_ai_chat(raw)
        task_id = str(uuid.uuid4())

        # Save task creation results to volume
        try:
            # Before saving, if there are uploaded files, annotate the AI result with attachment names
            annotated_result = result
            try:
                filenames = [secure_filename(getattr(f, 'filename', '') or f'file_{i}') for i, f in enumerate(uploaded_files)] if 'uploaded_files' in locals() else []
                # Try to parse AI result as JSON and attach filenames to each task
                if isinstance(result, str) and filenames:
                    parsed = None
                    try:
                        # Remove code fences and surrounding text, then find first JSON object/array
                        text = result.strip()
                        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
                        text = re.sub(r"\s*```$", "", text)
                        m = re.search(r"(\[.*?\]|\{.*?\})", text, flags=re.S)
                        if m:
                            json_text = m.group(0)
                            parsed = json.loads(json_text)
                    except Exception:
                        parsed = None

                    if isinstance(parsed, list):
                        for t in parsed:
                            if isinstance(t, dict):
                                t['attachment'] = filenames if len(filenames) > 1 else (filenames[0] if filenames else None)
                        annotated_result = parsed
                    elif isinstance(parsed, dict):
                        # single object -> attach and keep as dict (save_subtasks will wrap)
                        parsed['attachment'] = filenames if len(filenames) > 1 else (filenames[0] if filenames else None)
                        annotated_result = parsed
                elif isinstance(result, list) and uploaded_files:
                    filenames = [secure_filename(getattr(f, 'filename', '') or f'file_{i}') for i, f in enumerate(uploaded_files)]
                    for t in result:
                        if isinstance(t, dict):
                            t['attachment'] = filenames if len(filenames) > 1 else (filenames[0] if filenames else None)
                    annotated_result = result
            except Exception as e:
                app.logger.warning(f"Failed to annotate AI result with attachments: {e}")

            storage_result = save_task_results(original=raw, tasks_result=annotated_result, task_id=task_id)
            app.logger.info(f"Task storage: {storage_result}")
        except Exception as storage_error:
            app.logger.warning(f"Failed to save task results to volume: {storage_error}")
            storage_result = {"status": "error", "message": str(storage_error)}

        # If uploaded files are present and storage succeeded, save all files into the same folder
        files_saved = []
        if 'uploaded_files' in locals() and uploaded_files and storage_result.get("status") == "success":
            folder_path = storage_result.get("folder_path")
            if folder_path:
                for f in uploaded_files:
                    try:
                        filename = secure_filename(getattr(f, 'filename', '') or 'uploaded_file')
                        target = Path(folder_path) / filename
                        f.save(str(target))
                        app.logger.info(f"Saved uploaded file to: {target}")
                        files_saved.append(str(target))
                    except Exception as save_file_error:
                        app.logger.warning(f"Failed to save uploaded file {getattr(f,'filename',None)}: {save_file_error}")
            else:
                app.logger.warning("Storage reported success but no folder_path returned; uploaded files not saved")

        response_payload = {"taskId": task_id}
        if storage_result:
            response_payload["storage"] = storage_result
        if files_saved:
            response_payload["saved_files"] = files_saved

        return jsonify(response_payload), 200
    except Exception as e:
        app.logger.exception("Failed to analyze message")
        return jsonify({"error": "internal_error", "details": str(e)}), 500


@app.route('/receive-task-completion-result', methods=['POST'])
def receive_task_completion_result():    
    # Expect a JSON body containing 'taskId'. Find the task folder that contains this id in its name,
    # then look for a `Result artifacts` subfolder and enumerate files.
    try:
        if request.is_json:
            data = request.get_json(force=True)
        else:
            data = request.form.to_dict() or {}
    except Exception as e:
        app.logger.error(f"Failed to parse JSON/form payload: {e}")
        return jsonify({"error": "invalid_request", "details": str(e)}), 400

    task_id = data.get('taskId') or data.get('task_id')
    if not task_id:
        return jsonify({"error": "missing_task_id"}), 400

    tasks_root = Path('/data/tasks')
    if not tasks_root.exists():
        return jsonify({"error": "tasks_root_not_found", "path": str(tasks_root)}), 500

    # Find folders that contain the task_id in their name
    matches = [p for p in tasks_root.iterdir() if p.is_dir() and task_id in p.name]
    if not matches:
        return jsonify({"error": "task_folder_not_found", "taskId": task_id}), 404

    # Prefer the most recently modified matching folder
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    task_folder = matches[0]

    result_artifacts = task_folder / 'Result artifacts'
    if not result_artifacts.exists() or not result_artifacts.is_dir():
        return jsonify({"error": "result_artifacts_not_found", "folder": str(task_folder)}), 404

    test_result = {}
    source_code_parts = []
    image_file_path = None

    # Scan files and collect file contents according to naming patterns
    for f in sorted(result_artifacts.iterdir()):
        if not f.is_file():
            continue
        name = f.name
        # Source code files named like: 'Source Code_subtask_<index>'
        if name.startswith('Source Code_subtask_'):
            try:
                content = f.read_text(encoding='utf-8', errors='replace')
                source_code_parts.append(content)
            except Exception as e:
                app.logger.warning(f"Failed to read Source Code file {name}: {e}")
                source_code_parts.append("")
            continue
        # Test result files named like: 'Test result_subtask_<subtask_index>_test_<test_index>'
        if 'Test result_subtask_' in name:
            try:
                content = f.read_text(encoding='utf-8', errors='replace')
                test_result[name] = content
            except Exception as e:
                app.logger.warning(f"Failed to read Test result file {name}: {e}")
                test_result[name] = ""
            continue
        # Accept an image as completion_result (first found)
        if image_file_path is None and f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg'):
            image_file_path = f

    # Build response structure
    response = {
        "testResult": test_result,
        "sourceCode": "\n\n".join(source_code_parts) if source_code_parts else ""
    }

    # Add image information if exists
    if image_file_path:
        try:
            # Read image file as binary
            image_data = image_file_path.read_bytes()
            
            # Determine MIME type based on file extension
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.svg': 'image/svg+xml'
            }
            image_mime_type = mime_types.get(image_file_path.suffix.lower(), 'application/octet-stream')
            
            # Convert image data to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            response["image"] = {
                "filename": image_file_path.name,
                "mimeType": image_mime_type,
                "data": image_base64
            }
        except Exception as e:
            app.logger.error(f"Failed to process image file: {e}")
            response["image"] = None

    return jsonify(response), 200


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5000)
