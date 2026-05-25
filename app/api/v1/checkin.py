import random
import string
from datetime import datetime, timedelta

from flask import Blueprint, request

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from app.services.notification_service import create_notification
from models import Activity, ActivityCheckinCode, Checkin, Registration, User

bp = Blueprint("checkin", __name__, url_prefix="")
ACTIVE_STATUSES = ("registered", "re_registered")


def now():
    return datetime.utcnow()


def ensure_activity_owner(session, activity_id):
    activity = session.get(Activity, activity_id)
    if not activity:
        raise ApiError("活动不存在", code=404, status_code=404)
    if activity.organizer_id != request.current_user_id:
        raise ApiError("无权管理该活动", code=403, status_code=403)
    return activity


def random_code():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(6))


@bp.get("/organizer/activities/<int:activity_id>/checkin-code")
@bp.get("/activities/<int:activity_id>/checkin-code")
@role_required("organizer")
def get_checkin_code(activity_id):
    with db_session() as session:
        activity = ensure_activity_owner(session, activity_id)
        row = session.query(ActivityCheckinCode).filter(ActivityCheckinCode.activity_id == activity_id).first()
        if not row:
            row = ActivityCheckinCode(activity_id=activity_id, checkin_code=random_code())
            session.add(row)
            session.flush()
        return success({"checkin_code": row.checkin_code})


def checkin_window_error(activity):
    if now() < activity.start_time - timedelta(minutes=30):
        return "签到尚未开始"
    if now() > activity.end_time:
        return "签到已结束"
    return None


@bp.post("/activities/<int:path_activity_id>/checkin")
@bp.post("/checkin")
@role_required("user")
def code_checkin(path_activity_id=None):
    data = request.get_json(silent=True) or {}
    activity_id = path_activity_id or data.get("activity_id")
    checkin_code = str(data.get("checkin_code") or "").strip().upper()
    if not activity_id or not checkin_code:
        raise ApiError("缺少活动ID或签到码")

    with db_session() as session:
        activity = session.get(Activity, int(activity_id))
        if not activity:
            raise ApiError("活动不存在", code=404, status_code=404)
        code = session.query(ActivityCheckinCode).filter(ActivityCheckinCode.activity_id == activity.id).first()
        if not code or code.checkin_code.upper() != checkin_code:
            raise ApiError("签到码错误")
        if message := checkin_window_error(activity):
            raise ApiError(message)
        registration = (
            session.query(Registration)
            .filter(Registration.activity_id == activity.id, Registration.user_id == request.current_user_id)
            .first()
        )
        if not registration or registration.status not in ACTIVE_STATUSES:
            raise ApiError("只有已报名用户可以签到")
        if session.query(Checkin).filter(Checkin.activity_id == activity.id, Checkin.user_id == request.current_user_id).first():
            raise ApiError("你已完成签到，请勿重复签到")
        row = Checkin(activity_id=activity.id, user_id=request.current_user_id, checkin_method="code")
        session.add(row)
        session.flush()
        create_notification(
            session,
            "user",
            request.current_user_id,
            "Check-in Success",
            f"You checked in for {activity.name}.",
            "checkin_result",
            activity.id,
        )
        return success({"checkin_id": row.id, "checkin_time": dt(row.checkin_time)}, message="签到成功")


@bp.post("/organizer/activities/<int:activity_id>/manual-checkin")
@bp.post("/activities/<int:activity_id>/manual-checkin")
@role_required("organizer")
def manual_checkin(activity_id):
    data = request.get_json(silent=True) or {}
    student_id = str(data.get("student_id") or "").strip()
    if not student_id:
        raise ApiError("缺少学号")
    with db_session() as session:
        activity = ensure_activity_owner(session, activity_id)
        user = session.query(User).filter(User.student_id == student_id, User.status == "active").first()
        if not user:
            raise ApiError("用户不存在", code=404, status_code=404)
        registration = session.query(Registration).filter(Registration.activity_id == activity_id, Registration.user_id == user.id).first()
        if not registration or registration.status not in ACTIVE_STATUSES:
            raise ApiError("该用户未有效报名")
        if session.query(Checkin).filter(Checkin.activity_id == activity_id, Checkin.user_id == user.id).first():
            raise ApiError("该用户已完成签到")
        row = Checkin(activity_id=activity_id, user_id=user.id, checkin_method="manual", operator_id=request.current_user_id)
        session.add(row)
        session.flush()
        create_notification(
            session,
            "user",
            user.id,
            "Manual Check-in Success",
            f"Organizer completed manual check-in for {activity.name}.",
            "checkin_result",
            activity.id,
        )
        return success({"user_id": user.id, "checkin_time": dt(row.checkin_time)}, message="签到成功")


@bp.get("/user/checkins")
@bp.get("/checkin/my")
@role_required("user")
def my_checkins():
    with db_session() as session:
        rows = (
            session.query(Checkin)
            .join(Activity, Checkin.activity_id == Activity.id)
            .filter(Checkin.user_id == request.current_user_id)
            .order_by(Checkin.checkin_time.desc())
            .all()
        )
        return success(
            {
                "total": len(rows),
                "list": [
                    {
                        "activity_id": row.activity_id,
                        "activity_name": row.activity.name,
                        "activity_start_time": dt(row.activity.start_time),
                        "checkin_time": dt(row.checkin_time),
                        "checkin_method": row.checkin_method,
                    }
                    for row in rows
                ],
            }
        )


@bp.get("/organizer/activities/<int:activity_id>/checkins")
@bp.get("/activities/<int:activity_id>/checkin-stats")
@role_required("organizer")
def checkin_stats(activity_id):
    with db_session() as session:
        ensure_activity_owner(session, activity_id)
        total_registered = (
            session.query(Registration)
            .filter(Registration.activity_id == activity_id, Registration.status.in_(ACTIVE_STATUSES))
            .count()
        )
        rows = (
            session.query(Checkin)
            .join(User, Checkin.user_id == User.id)
            .filter(Checkin.activity_id == activity_id)
            .order_by(Checkin.checkin_time.desc())
            .all()
        )
        checked_user_ids = [row.user_id for row in rows]
        not_checked_query = session.query(Registration).join(User, Registration.user_id == User.id).filter(
            Registration.activity_id == activity_id,
            Registration.status.in_(ACTIVE_STATUSES),
        )
        if checked_user_ids:
            not_checked_query = not_checked_query.filter(~Registration.user_id.in_(checked_user_ids))
        not_checked_rows = not_checked_query.order_by(Registration.registration_time.asc()).all()
        checked_in = len(rows)
        return success(
            {
                "total_registered": total_registered,
                "checked_in": checked_in,
                "not_checked_in": max(total_registered - checked_in, 0),
                "checkin_rate": f"{(checked_in / total_registered * 100) if total_registered else 0:.2f}%",
                "checkin_list": [
                    {
                        "user_id": row.user.id,
                        "student_id": row.user.student_id,
                        "username": row.user.username,
                        "checkin_time": dt(row.checkin_time),
                        "checkin_method": row.checkin_method,
                    }
                    for row in rows
                ],
                "notCheckedIn": [
                    {
                        "user_id": row.user.id,
                        "student_id": row.user.student_id,
                        "username": row.user.username,
                        "registration_time": dt(row.registration_time),
                    }
                    for row in not_checked_rows
                ],
            }
        )
