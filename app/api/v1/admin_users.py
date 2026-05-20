from flask import Blueprint, request
from werkzeug.security import generate_password_hash

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from models import Admin, Organizer, User

bp = Blueprint("admin_users", __name__, url_prefix="/admin")


def parse_page_args():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError) as exc:
        raise ApiError("分页参数无效") from exc
    return page, page_size


def require_super_admin(session):
    admin = session.get(Admin, request.current_user_id)
    if not admin or admin.status == "deleted":
        raise ApiError("管理员不存在或已删除", code=404, status_code=404)
    if admin.role != "super_admin":
        raise ApiError("需要超级管理员权限", code=403, status_code=403)
    return admin


def next_admin_no(session):
    max_no = 0
    for (admin_no,) in session.query(Admin.admin_no).all():
        if admin_no and str(admin_no).isdigit():
            max_no = max(max_no, int(admin_no))
    return f"{max_no + 1:06d}"


@bp.get("/users")
@role_required("admin")
def list_users():
    page, page_size = parse_page_args()
    student_id = str(request.args.get("student_id") or "").strip()
    college = str(request.args.get("college") or "").strip()

    with db_session() as session:
        query = session.query(User).filter(User.status != "deleted")
        if student_id:
            query = query.filter(User.student_id.contains(student_id))
        if college:
            query = query.filter(User.college.contains(college))

        total = query.count()
        rows = (
            query.order_by(User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return success(
            {
                "total": total,
                "page": page,
                "page_size": page_size,
                "list": [
                    {
                        "user_id": row.id,
                        "student_id": row.student_id,
                        "email": row.email,
                        "college": row.college,
                        "major": row.major,
                        "grade": row.grade,
                        "status": row.status,
                    }
                    for row in rows
                ],
            }
        )


@bp.get("/users/<int:user_id>")
@role_required("admin")
def get_user_detail(user_id):
    with db_session() as session:
        user = session.get(User, user_id)
        if not user or user.status == "deleted":
            raise ApiError("用户不存在", code=404, status_code=404)
        return success(
            {
                "user_id": user.id,
                "student_id": user.student_id,
                "email": user.email,
                "gender": user.gender,
                "college": user.college,
                "major": user.major,
                "grade": user.grade,
                "status": user.status,
            }
        )


@bp.get("/organizers")
@role_required("admin")
def list_organizers():
    page, page_size = parse_page_args()
    org_name = str(request.args.get("org_name") or "").strip()
    status = str(request.args.get("status") or "").strip()

    with db_session() as session:
        query = session.query(Organizer)
        if status:
            query = query.filter(Organizer.status == status)
        else:
            query = query.filter(Organizer.status != "deleted")
        if org_name:
            query = query.filter(Organizer.org_name.contains(org_name))

        total = query.count()
        rows = (
            query.order_by(Organizer.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return success(
            {
                "total": total,
                "list": [
                    {
                        "organizer_id": row.id,
                        "email": row.email,
                        "org_name": row.org_name,
                        "status": row.status,
                    }
                    for row in rows
                ],
            }
        )


@bp.get("/organizers/<int:organizer_id>")
@role_required("admin")
def get_organizer_detail(organizer_id):
    with db_session() as session:
        organizer = session.get(Organizer, organizer_id)
        if not organizer or organizer.status == "deleted":
            raise ApiError("组织者不存在", code=404, status_code=404)
        return success(
            {
                "organizer_id": organizer.id,
                "email": organizer.email,
                "org_name": organizer.org_name,
                "org_proof_text": organizer.org_proof_text,
                "org_proof_image": organizer.org_proof_image,
                "submitted_at": None,
                "status": organizer.status,
                "avatar": organizer.avatar,
                "reject_reason": organizer.reject_reason or "",
            }
        )


@bp.put("/organizers/<int:organizer_id>/review")
@role_required("admin")
def review_organizer(organizer_id):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip()
    reject_reason = str(data.get("reject_reason") or "").strip()

    if action not in ("approve", "reject"):
        raise ApiError("action无效")
    if action == "reject" and not reject_reason:
        raise ApiError("reject_reason必填")

    with db_session() as session:
        organizer = session.get(Organizer, organizer_id)
        if not organizer or organizer.status == "deleted":
            raise ApiError("组织者不存在", code=404, status_code=404)

        if action == "approve":
            organizer.status = "approved"
            organizer.reject_reason = None
        else:
            organizer.status = "rejected"
            organizer.reject_reason = reject_reason

        return success(
            {"organizer_id": organizer.id, "status": organizer.status},
            message="审核完成",
        )


@bp.post("/admins")
@role_required("admin")
def create_admin():
    data = request.get_json(silent=True) or {}
    required_fields = ["email", "password", "username", "role"]
    missing = [field for field in required_fields if not str(data.get(field) or "").strip()]
    if missing:
        raise ApiError(f"缺少必填字段：{', '.join(missing)}")

    role = str(data.get("role")).strip()
    if role not in ("admin", "super_admin"):
        raise ApiError("role无效")

    with db_session() as session:
        require_super_admin(session)
        email = str(data["email"]).strip()
        if session.query(Admin).filter(Admin.email == email).first():
            raise ApiError("邮箱已存在")

        admin = Admin(
            admin_no=next_admin_no(session),
            email=email,
            password=generate_password_hash(str(data["password"])),
            username=str(data["username"]).strip(),
            role=role,
            status="active",
        )
        session.add(admin)
        session.flush()

        return success(
            {"admin_id": admin.id, "admin_no": admin.admin_no},
            message="管理员创建成功",
        )


@bp.get("/admins")
@role_required("admin")
def list_admins():
    with db_session() as session:
        rows = (
            session.query(Admin)
            .filter(Admin.status != "deleted")
            .order_by(Admin.id.asc())
            .all()
        )

        return success(
            [
                {
                    "admin_id": row.id,
                    "admin_no": row.admin_no,
                    "email": row.email,
                    "username": row.username,
                    "role": row.role,
                    "status": row.status,
                    "created_at": None,
                }
                for row in rows
            ]
        )


@bp.delete("/admins/<int:admin_id>")
@role_required("admin")
def delete_admin(admin_id):
    with db_session() as session:
        require_super_admin(session)
        target = session.get(Admin, admin_id)
        if not target or target.status == "deleted":
            raise ApiError("管理员不存在", code=404, status_code=404)
        if target.role == "super_admin":
            raise ApiError("超级管理员不可删除")

        target.status = "deleted"
        return success(None, message="管理员已删除")
