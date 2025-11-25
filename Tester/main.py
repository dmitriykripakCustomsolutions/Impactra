import json
import os
import re
import sys
from pathlib import Path
from flask import Flask, request, jsonify
from test_generator import generate_and_run_unit_tests

# Ensure shared module is importable (local dev and Docker)
shared_paths = [
    Path(__file__).parent.parent,  # local: repo root contains 'shared'
    Path('/app'),  # docker: /app/shared
]
for p in shared_paths:
    if p.exists():
        sys.path.insert(0, str(p))
        break
from shared import find_task_folder, RESULT_ARTIFACTS_FOLDER

app = Flask(__name__)

@app.route('/test-source-code', methods=['POST'])
def test_source_code():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        app.logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({"error": "invalid_json", "details": str(e)}), 400

    if not data:
        return jsonify({"error": "No data provided"}), 400

    task_id = data.get('task_id') or data.get('taskId')
    if not task_id:
        return jsonify({"error": "No 'task_id' provided"}), 400

    use_ai = data.get('useAI', True)

    try:
        # Locate task folder using shared helper
        task_folder = find_task_folder(task_id)
        result_artifacts_path = os.path.join(task_folder, RESULT_ARTIFACTS_FOLDER)

        if not os.path.isdir(result_artifacts_path):
            app.logger.warning(f"Result artifacts folder not found: {result_artifacts_path}")
            return jsonify({"test_results": []}), 200

        # Find source code files matching pattern: Source Code_subtask_<index>.<ext>
        all_files = [f for f in os.listdir(result_artifacts_path) if f.startswith('Source Code_subtask_')]
        if not all_files:
            app.logger.info(f"No source code files found in: {result_artifacts_path}")
            return jsonify({"test_results": []}), 200

        # Helper to extract subtask index from filename
        def _extract_subtask_index(fname: str) -> int:
            m = re.search(r'_subtask_(\d+)\.', fname)
            if m:
                return int(m.group(1))
            return -1

        # Sort files by subtask index then by name
        all_files.sort(key=lambda fn: (_extract_subtask_index(fn), fn))

        aggregated_results = []

        for subtask_index, filename in enumerate(all_files):
            file_path = os.path.join(result_artifacts_path, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()
            except Exception as e:
                app.logger.error(f"Failed to read source file {file_path}: {e}")
                continue

            try:
                # Generate and run tests (returns JSON string)
                test_results_json = generate_and_run_unit_tests(source_code, use_ai=use_ai)
                test_results = json.loads(test_results_json)

                # Save each test result into separate files
                for test_idx, test_obj in enumerate(test_results):
                    out_name = f"Test result_subtask_{_extract_subtask_index(filename)}_test_{test_idx}.json"
                    out_path = os.path.join(result_artifacts_path, out_name)
                    try:
                        with open(out_path, 'w', encoding='utf-8') as of:
                            json.dump(test_obj, of, indent=2)
                    except Exception as e:
                        app.logger.error(f"Failed to write test result file {out_path}: {e}")

                # Append to aggregated results
                aggregated_results.append({
                    "source_file": filename,
                    "tests": test_results
                })

            except Exception as e:
                app.logger.exception(f"Failed to generate/run tests for {filename}")
                aggregated_results.append({
                    "source_file": filename,
                    "tests": [],
                    "error": str(e)
                })

        return jsonify({"test_results": aggregated_results}), 200

    except FileNotFoundError as e:
        app.logger.error(f"Task folder not found for taskId {task_id}: {e}")
        return jsonify({"error": "task_not_found", "details": str(e)}), 404
    except Exception as e:
        app.logger.exception("Failed to process test request")
        return jsonify({"error": "internal_error", "details": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)
