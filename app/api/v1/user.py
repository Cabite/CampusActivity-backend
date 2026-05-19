from flask import Blueprint, request
from werkzeug.security import generate_password_hash

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from models import Admin, Organizer, User

bp = Blueprint("user", __name__, url_prefix="/user")


def current_entity(session):
    role = request.current_role
    user_id = request.current_user_id
    model = {"user": User, "organizer": Organizer, "admin": Admin}[role]
    entity = session.get(model, user_id)
    if not entity or entity.status == "deleted":
        raise ApiError("账号不存在或已注销", code=404, status_code=404)
    return role, entity


@bp.get("/profile")
@role_required("user", "organizer", "admin")
def profile():
    with db_session() as session:
        role, entity = current_entity(session)
        if role == "user":
            data = {
                "user_id": entity.id,
                "student_id": entity.student_id,
                "email": entity.email,
                "username": entity.username,
                "avatar": entity.avatar,
                "gender": entity.gender,
                "college": entity.college,
                "major": entity.major,
                "grade": entity.grade,
                "phone": entity.phone,
                "status": entity.status,
                "achievement": {"title": "初级探索者", "effective_participation_count": 0},
            }
        elif role == "organizer":
            data = {
                "organizer_id": entity.id,
                "email": entity.email,
                "org_name": entity.org_name,
                "avatar": entity.avatar,
                "status": entity.status,
                "reject_reason": entity.reject_reason,
                "org_proof_text": entity.org_proof_text,
                "org_proof_image": entity.org_proof_image,
            }
        else:
            data = {
                "admin_id": entity.id,
                "admin_no": entity.admin_no,
                "email": entity.email,
                "username": entity.username,
                "avatar": entity.avatar,
                "role": entity.role,
            }
        return success(data)


@bp.put("/profile")
@role_required("user", "organizer", "admin")
def update_profile():
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        role, entity = current_entity(session)
        if role == "user":
            for field in ["username", "gender", "college", "major", "grade", "phone", "avatar"]:
                if field in data:
                    setattr(entity, field, str(data[field]).strip() or None)
        else:
            if "avatar" in data:
                entity.avatar = str(data["avatar"]).strip() or None
            if data.get("password"):
                entity.password = generate_password_hash(str(data["password"]))
        return success(None, message="更新成功")


@bp.delete("/account")
@role_required("user", "organizer", "admin")
def delete_account():
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        raise ApiError("请确认注销账号")
    with db_session() as session:
        role, entity = current_entity(session)
        if role == "admin" and entity.role == "super_admin":
            raise ApiError("超级管理员账号不可注销")
        entity.status = "deleted"
        return success(None, message="账号已注销")
