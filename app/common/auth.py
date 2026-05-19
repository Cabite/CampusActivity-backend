from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import current_app, request

from app.common.errors import ApiError


def create_token(role, user_id):
    now = datetime.utcnow()
    payload = {
        "role": role,
        "user_id": user_id,
        "iat": now,
        "exp": now + timedelta(hours=2),
    }
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")
    return token


def decode_token(token):
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("登录已过期，请重新登录", code=401, status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("登录状态无效，请重新登录", code=401, status_code=401) from exc


def get_current_identity():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError("请先登录", code=401, status_code=401)
    payload = decode_token(header.replace("Bearer ", "", 1).strip())
    return payload["role"], int(payload["user_id"])


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            role, user_id = get_current_identity()
            if role not in roles:
                raise ApiError("无权访问该接口", code=403, status_code=403)
            request.current_role = role
            request.current_user_id = user_id
            return func(*args, **kwargs)

        return wrapper

    return decorator
