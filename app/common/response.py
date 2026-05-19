from flask import jsonify


def success(data=None, message="success", code=200):
    return jsonify({
        "code": code,
        "message": message,
        "data": data,
    })


def fail(message, code=400, data=None):
    return jsonify({
        "code": code,
        "message": message,
        "data": data,
    })
