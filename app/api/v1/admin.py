from collections import Counter
from datetime import datetime

from flask import Blueprint, request
from werkzeug.security import generate_password_hash

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from app.services.notification_service import create_notification
from models import Activity, Admin, Category, Checkin, Organizer, Registration, User

bp = Blueprint("admin", __name__, url_prefix="/admin")


def require_super_admin(session):
    admin = session.get(Admin, request.current_user_id)
    if not admin or admin.role != "super_admin":
        raise ApiError("仅超级管理员可操作", code=403, status_code=403)
    return admin


def next_admin_no(session):
    max_no = 0
    for row in session.query(Admin.admin_no).all():
        try:
            max_no = max(max_no, int(row[0]))
        except (TypeError, ValueError):
            continue
    return f"{max_no + 1:06d}"


@bp.get("/activities/")
@bp.get("/activities")
@role_required("admin")
def pending_activities():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    with db_session() as session:
        query = session.query(Activity).filter(Activity.status.in_(("pending", "edit_pending")))
        total = query.count()
        rows = query.order_by(Activity.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return success(
            {
                "total": total,
                "page": page,
                "page_size": page_size,
                "list": [
                    {
                        "activity_id": row.id,
                        "name": row.name,
                        "organizer_id": row.organizer_id,
                        "organizer_name": row.organizer.org_name if row.organizer else None,
                        "start_time": dt(row.start_time),
                        "category_name": row.category.name if row.category else None,
                        "category_path": row.category.name if row.category else None,
                        "status": row.status,
                    }
                    for row in rows
                ],
            }
        )


@bp.put("/activities/<int:activity_id>/review")
@role_required("admin")
def review_activity(activity_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    with db_session() as session:
        activity = session.get(Activity, activity_id)
        if not activity:
            raise ApiError("活动不存在", code=404, status_code=404)
        if action == "approve":
            activity.status = "open"
            message = "审核通过"
        elif action == "reject":
            reason = str(data.get("reject_reason") or "").strip()
            if not reason:
                raise ApiError("reject_reason is required")
            activity.status = "rejected"
            activity.reject_reason = reason
            message = "审核不通过"
        else:
            raise ApiError("action must be approve or reject")
        create_notification(session, "organizer", activity.organizer_id, "Activity Review Result", f"{activity.name}: {message}", "activity_audit_result", activity.id)
        return success({"activity_id": activity.id, "new_status": activity.status}, message=message)


@bp.put("/activities/<int:activity_id>/remove")
@role_required("admin")
def remove_activity(activity_id):
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()
    with db_session() as session:
        activity = session.get(Activity, activity_id)
        if not activity:
            raise ApiError("活动不存在", code=404, status_code=404)
        activity.status = "removed"
        activity.reject_reason = reason
        create_notification(session, "organizer", activity.organizer_id, "Activity Removed", f"{activity.name} was removed. Reason: {reason}", "violation_result", activity.id)
        rows = session.query(Registration).filter(Registration.activity_id == activity.id).all()
        for row in rows:
            create_notification(session, "user", row.user_id, "Activity Removed", f"{activity.name} was removed. Reason: {reason}", "violation_result", activity.id)
        return success(None, message="活动已下架，已通知发布者和所有报名用户")


@bp.get("/users")
@role_required("admin")
def list_users():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    with db_session() as session:
        query = session.query(User)
        total = query.count()
        rows = query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return success({"total": total, "page": page, "page_size": page_size, "list": [{"user_id": row.id, "student_id": row.student_id, "email": row.email, "college": row.college, "major": row.major, "grade": row.grade, "status": row.status} for row in rows]})


@bp.get("/users/<int:user_id>")
@role_required("admin")
def user_detail(user_id):
    with db_session() as session:
        row = session.get(User, user_id)
        if not row:
            raise ApiError("用户不存在", code=404, status_code=404)
        return success({"user_id": row.id, "student_id": row.student_id, "email": row.email, "gender": row.gender, "college": row.college, "major": row.major, "grade": row.grade, "status": row.status})


@bp.get("/organizers")
@role_required("admin")
def list_organizers():
    with db_session() as session:
        rows = session.query(Organizer).order_by(Organizer.id.desc()).all()
        return success({"total": len(rows), "list": [{"organizer_id": row.id, "email": row.email, "org_name": row.org_name, "status": row.status} for row in rows]})


@bp.get("/organizers/<int:organizer_id>")
@role_required("admin")
def organizer_detail(organizer_id):
    with db_session() as session:
        row = session.get(Organizer, organizer_id)
        if not row:
            raise ApiError("组织者不存在", code=404, status_code=404)
        return success({"organizer_id": row.id, "email": row.email, "org_name": row.org_name, "org_proof_text": row.org_proof_text, "org_proof_image": row.org_proof_image, "status": row.status, "avatar": row.avatar, "reject_reason": row.reject_reason})


@bp.put("/organizers/<int:organizer_id>/review")
@role_required("admin")
def review_organizer(organizer_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    with db_session() as session:
        row = session.get(Organizer, organizer_id)
        if not row:
            raise ApiError("组织者不存在", code=404, status_code=404)
        if action == "approve":
            row.status = "approved"
            row.reject_reason = None
        elif action == "reject":
            row.status = "rejected"
            row.reject_reason = str(data.get("reject_reason") or "")
        else:
            raise ApiError("action must be approve or reject")
        create_notification(session, "organizer", row.id, "Organizer Review Result", f"Organizer review result: {row.status}", "organizer_audit_result", row.id)
        return success({"organizer_id": row.id, "status": row.status}, message="审核完成")


@bp.post("/admins")
@role_required("admin")
def create_admin():
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        require_super_admin(session)
        admin = Admin(admin_no=next_admin_no(session), email=str(data.get("email") or "").strip(), password=generate_password_hash(str(data.get("password") or "")), username=str(data.get("username") or "").strip(), role=data.get("role") or "admin", status="active")
        if not admin.email or not data.get("password") or not admin.username:
            raise ApiError("email, password and username are required")
        session.add(admin)
        session.flush()
        return success({"admin_id": admin.id, "admin_no": admin.admin_no}, message="管理员创建成功")


@bp.get("/admins")
@role_required("admin")
def list_admins():
    with db_session() as session:
        rows = session.query(Admin).order_by(Admin.id.asc()).all()
        return success([{"admin_id": row.id, "admin_no": row.admin_no, "email": row.email, "username": row.username, "role": row.role, "status": row.status} for row in rows])


@bp.delete("/admins/<int:admin_id>")
@role_required("admin")
def delete_admin(admin_id):
    with db_session() as session:
        require_super_admin(session)
        row = session.get(Admin, admin_id)
        if not row:
            raise ApiError("管理员不存在", code=404, status_code=404)
        if row.role == "super_admin":
            raise ApiError("超级管理员不可删除")
        row.status = "deleted"
        return success(None, message="管理员已删除")


@bp.get("/statistics")
@role_required("admin")
def platform_statistics():
    with db_session() as session:
        activities = session.query(Activity).all()
        users = session.query(User).count()
        organizers = session.query(Organizer).count()
        admins = session.query(Admin).count()
        registrations = session.query(Registration).count()
        checked = session.query(Checkin).count()
        categories = {row.name: 0 for row in session.query(Category).filter(Category.parent_id == 0).all()}
        for activity in activities:
            if activity.category:
                categories[activity.category.name] = categories.get(activity.category.name, 0) + 1
        return success({"activities": {"total": len(activities), "by_statuss": dict(Counter(row.status for row in activities)), "by_categories": categories}, "user": {"total": users + organizers + admins, "student": users, "organize": organizers, "admin": admins}, "total_participation_count": registrations, "average_checkin_rate": f"{(checked / registrations * 100) if registrations else 0:.1f}%"})
