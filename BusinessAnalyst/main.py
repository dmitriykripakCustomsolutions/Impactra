import logging
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/receive-message', methods=['POST'])
def receive_message():
    #TODO implement actual message handling logic here  

    # if request.is_json:
    #     data = request.get_json()
    #     message = data.get('message', '')
    # else:
    #     # If form-urlencoded
    #     message = request.form.get('message', '')
    # app.logger.info(f"A message received: {message}")
    # return jsonify({"status": "ok", "received": message}), 200
    return jsonify({"message": "\'receive-message\' Endpoint works"})

@app.route('/receive-task-completion-result', methods=['POST'])
def receive_task_completion_result():

    #TODO implement actual message handling logic here  

    # if request.is_json:
    #     data = request.get_json()
    #     message = data.get('message', '')
    # else:
    #     # If form-urlencoded
    #     message = request.form.get('message', '')
    # app.logger.info(f"A message received: {message}")
    # return jsonify({"status": "ok", "received": message}), 200
    return jsonify({"message": "\'receive-task-completion-result\' Endpoint works"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
