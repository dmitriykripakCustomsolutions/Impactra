import logging
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/run-code', methods=['POST'])
def receive_message():
    # "completionResult": result
    return jsonify({"message": "\'run-code\' Endpoint works"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
