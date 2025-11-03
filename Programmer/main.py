import logging
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/process-task', methods=['POST'])
def receive_message():
    app.logger.info(f"\'process-task\' Endpoint works")
    # if request.is_json:
    #     data = request.get_json()
    #     message = data.get('message', '')
    # else:
    #     # If form-urlencoded
    #     message = request.form.get('message', '')
    # app.logger.info(f"A message received: {message}")
    # return jsonify({"status": "ok", "received": message}), 200
    return "\'process-task\' Endpoint works"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
