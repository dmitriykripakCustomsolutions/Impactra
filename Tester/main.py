import json
from flask import Flask, request, jsonify
from test_generator import generate_and_run_unit_tests

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
    
    compiled = data.get('compiled', '')
    error = data.get('error', '')
    sourceCode = data.get('sourceCode', '')

    if not sourceCode:
        return jsonify({"error": "No 'sourceCode' provided"}), 400
    
    if not compiled:
        return jsonify({"error": "Unable to compile provided source code"}), 400
    
    if error:
        return jsonify({"error": "Source code contains errors", "details": error}), 400
    
    
    # Optional: allow client to specify whether to use AI for test generation
    use_ai = data.get('useAI', True)
    
    try:
        # Generate and run unit tests
        test_results_json = generate_and_run_unit_tests(sourceCode, use_ai=use_ai)
        test_results = json.loads(test_results_json)
        
        # test_results_mock = {'testDescription': 'Test with unsorted array of positive integers',
        #                        'testCases': [64, 34, 25, 12, 22, 11, 90],
        #                        'isTestPassed': False,
        #                        'completionResultValues': 
        #                            [64, 34, 25, 12, 22, 11, 90]
        #                        }
        # return jsonify({"test_results": test_results_mock}), 200

        return jsonify({"test_results": test_results}), 200
    except Exception as e:
        app.logger.exception("Failed to generate and run tests")
        return jsonify({"error": "internal_error", "details": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)
