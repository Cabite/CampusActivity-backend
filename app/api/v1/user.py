import re
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, request, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from models import Admin, Checkin, Organizer, User

bp = Blueprint("user", __name__, url_prefix="/user")

AVATAR_MAX_SIZE = 2 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
AVATAR_ALLOWED_MIMETYPES = {"image/jpeg", "image/png"}

ACHIEVEMENT_LEVELS = [
    {"title": "初级探索者", "required_count": 5},
    {"title": "中级探索者", "required_count": 20},
    {"title": "高级探索者", "required_count": 30},
]


def current_entity(session):
    role = request.current_role
    user_id = request.current_user_id
    model = {"user": User, "organizer": Organizer, "admin": Admin}[role]
    entity = session.get(model, user_id)
    if not entity or entity.status == "deleted":
        raise ApiError("账号不存在或已注销", code=404, status_code=404)
    return role, entity


def achievement_for_count(effective_count):
    title = "无"
    for level in ACHIEVEMENT_LEVELS:
        if effective_count >= level["required_count"]:
            title = level["title"]
        else:
            break
    return {"title": title, "effective_participation_count": effective_count}


def normalize_optional_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_optional_phone(value):
    phone = normalize_optional_text(value)
    if phone is not None and not re.fullmatch(r"1\d{10}", phone):
        raise ApiError("手机号须为11位")
    return phone


def require_non_empty_text(data, field):
    value = str(data.get(field) or "").strip()
    if not value:
        raise ApiError(f"{field}不能为空")
    return value


def avatar_upload_dir():
    root = Path(current_app.root_path) / "static" / "avatars"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_avatar_file(file_storage):
    if not file_storage or not file_storage.filename:
        raise ApiError("请上传头像文件")
    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in AVATAR_ALLOWED_EXTENSIONS or file_storage.mimetype not in AVATAR_ALLOWED_MIMETYPES:
        raise ApiError("头像仅支持jpg/png格式")

    stream = file_storage.stream
    current_position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(current_position)
    if size > AVATAR_MAX_SIZE:
        raise ApiError("头像文件不能超过2MB")
    return extension


def save_avatar_file(file_storage, role, user_id):
    extension = validate_avatar_file(file_storage)
    filename = f"{role}_{user_id}_{uuid4().hex}.{extension}"
    target = avatar_upload_dir() / filename
    file_storage.save(target)
    return url_for("static", filename=f"avatars/{filename}", _external=False)


@bp.get("/profile")
@role_required("user", "organizer", "admin")
def profile():
    with db_session() as session:
        role, entity = current_entity(session)
        if role == "user":
            effective_count = session.query(Checkin).filter(Checkin.user_id == entity.id).count()
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
                "achievement": achievement_for_count(effective_count),
            }
        elif role == "organizer":
            data = {
                "organizer_id": entity.id,
                "email": entity.email,
                "org_name": entity.org_name,
                "avatar": entity.avatar,
                "status": entity.status,
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
            for field in ["username", "gender", "college", "major", "grade"]:
                if field in data:
                    setattr(entity, field, require_non_empty_text(data, field))
            if "phone" in data:
                entity.phone = normalize_optional_phone(data.get("phone"))
            if "avatar" in data:
                entity.avatar = normalize_optional_text(data.get("avatar"))
        else:
            if "avatar" in data:
                entity.avatar = normalize_optional_text(data.get("avatar"))
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


@bp.post("/avatar")
@role_required("user", "organizer", "admin")
def update_avatar():
    with db_session() as session:
        role, entity = current_entity(session)
        file_storage = request.files.get("avatar")
        if file_storage:
            avatar = save_avatar_file(file_storage, role, entity.id)
        else:
            data = request.get_json(silent=True) or {}
            avatar = str(data.get("avatar") or data.get("avatar_url") or "").strip()
            if not avatar:
                raise ApiError("请上传头像文件")
        entity.avatar = avatar
        return success({"avatar_url": avatar}, message="头像更新成功")


@bp.post("/reset-password")
@role_required("user", "organizer", "admin")
def reset_password():
    data = request.get_json(silent=True) or {}
    new_password = str(data.get("new_password") or "")
    confirm_password = str(data.get("confirm_password") or "")
    if not new_password:
        raise ApiError("new_password is required")
    if new_password != confirm_password:
        raise ApiError("两次密码不一致")
    with db_session() as session:
        role, entity = current_entity(session)
        entity.password = generate_password_hash(new_password)
        return success(None, message="密码重置成功")
