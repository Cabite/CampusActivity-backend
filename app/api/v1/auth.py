import re

from flask import Blueprint, request
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

from app.common.auth import create_token, role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from models import Admin, Organizer, User

bp = Blueprint("auth", __name__, url_prefix="/auth")


def payload():
    return request.get_json(silent=True) or {}


def require_fields(data, fields):
    missing = [field for field in fields if not str(data.get(field, "")).strip()]
    if missing:
        raise ApiError(f"缺少必填字段：{', '.join(missing)}")


def normalize_optional_phone(value):
    phone = str(value or "").strip()
    if not phone:
        return None
    if not re.fullmatch(r"1\d{10}", phone):
        raise ApiError("手机号须为11位")
    return phone


@bp.post("/register/user")
def register_user():
    data = payload()
    require_fields(
        data,
        ["student_id", "email", "username", "password", "confirm_password", "gender", "college", "major", "grade"],
    )
    student_id = str(data["student_id"]).strip()
    email = str(data["email"]).strip()

    if not re.fullmatch(r"\d{10}", student_id):
        raise ApiError("学号必须为10位数字")
    if data["password"] != data["confirm_password"]:
        raise ApiError("两次密码不一致")

    with db_session() as session:
        if session.query(User).filter(User.student_id == student_id).first():
            raise ApiError("学号已存在")
        if session.query(User).filter(User.email == email).first():
            raise ApiError("邮箱已注册")

        user = User(
            student_id=student_id,
            email=email,
            username=str(data["username"]).strip(),
            password=generate_password_hash(str(data["password"])),
            gender=str(data["gender"]).strip(),
            college=str(data["college"]).strip(),
            major=str(data["major"]).strip(),
            grade=str(data["grade"]).strip(),
            phone=normalize_optional_phone(data.get("phone")),
            status="active",
        )
        session.add(user)
        session.flush()
        token = create_token("user", user.id)
        return success(
            {"userId": user.id, "user_id": user.id, "role": "user", "status": user.status, "token": token},
            message="注册成功，已自动登录",
        )


@bp.post("/register/organizer")
def register_organizer():
    data = payload()
    require_fields(data, ["email", "org_name", "password", "confirm_password", "org_proof_text"])
    if data["password"] != data["confirm_password"]:
        raise ApiError("两次密码不一致")

    email = str(data["email"]).strip()
    with db_session() as session:
        if session.query(Organizer).filter(Organizer.email == email).first():
            raise ApiError("邮箱已注册")
        organizer = Organizer(
            email=email,
            org_name=str(data["org_name"]).strip(),
            password=generate_password_hash(str(data["password"])),
            org_proof_text=str(data["org_proof_text"]).strip(),
            org_proof_image=str(data.get("org_proof_image") or "").strip() or None,
            status="pending",
        )
        session.add(organizer)
        session.flush()
        token = create_token("organizer", organizer.id)
        return success(
            {
                "userId": organizer.id,
                "organizer_id": organizer.id,
                "role": "organizer",
                "token": token,
            },
            message="注册成功，自动登录，请等待管理员审核",
        )


@bp.post("/login")
def login():
    data = payload()
    require_fields(data, ["role", "account", "password"])

    role = str(data["role"]).strip()
    account = str(data["account"]).strip()
    password = str(data["password"])

    with db_session() as session:
        if role == "user":
            entity = session.query(User).filter(or_(User.student_id == account, User.email == account)).first()
        elif role == "organizer":
            entity = session.query(Organizer).filter(Organizer.email == account).first()
        elif role == "admin":
            entity = session.query(Admin).filter(Admin.admin_no == account).first()
        else:
            raise ApiError("角色类型无效")

        if not entity or entity.status == "deleted":
            raise ApiError("账号或密码错误", code=401, status_code=401)
        if not check_password_hash(entity.password, password):
            raise ApiError("账号或密码错误", code=401, status_code=401)

        return success(
            {
                "token": create_token(role, entity.id),
                "user_id": entity.id,
                "role": role,
                "expires_in": 7200,
            },
            message="登录成功",
        )


@bp.post("/logout")
@role_required("user", "organizer", "admin")
def logout():
    return success(None, message="退出成功")
