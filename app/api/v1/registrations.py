from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, request

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from models import Activity, Checkin, Registration, User

bp = Blueprint("registrations", __name__, url_prefix="")

ACTIVE_STATUSES = ("registered", "re_registered")


def now():
    return datetime.utcnow()


def active_count(session, activity_id):
    return (
        session.query(Registration)
        .filter(Registration.activity_id == activity_id, Registration.status.in_(ACTIVE_STATUSES))
        .count()
    )


def refresh_participants(session, activity):
    activity.current_participants = active_count(session, activity.id)


def remaining_slots(session, activity):
    refresh_participants(session, activity)
    return max(activity.max_participants - activity.current_participants, 0)


@bp.post("/registrations")
@role_required("user")
def register_activity():
    data = request.get_json(silent=True) or {}
    activity_id = data.get("activity_id")
    if not activity_id:
        raise ApiError("缺少活动ID")

    with db_session() as session:
        activity = session.get(Activity, int(activity_id))
        if not activity:
            raise ApiError("活动不存在", code=404, status_code=404)
        if activity.status != "open":
            raise ApiError("当前活动不可报名")
        if now() > activity.registration_deadline:
            raise ApiError("报名已截止")
        if remaining_slots(session, activity) <= 0:
            raise ApiError("当前活动报名人数已满")

        row = (
            session.query(Registration)
            .filter(Registration.activity_id == activity.id, Registration.user_id == request.current_user_id)
            .first()
        )
        if row:
            if row.status in ACTIVE_STATUSES:
                raise ApiError("你已报名该活动，请勿重复报名")
            if row.status == "blocked" or row.reject_count >= 2:
                raise ApiError("你已被这活动拒绝两次，不可再报名！")
            if row.status == "rejected":
                if row.last_reject_time and now() < row.last_reject_time + timedelta(minutes=10):
                    raise ApiError("报名被拒绝后10分钟内不可再次报名")
                row.status = "re_registered"
            elif row.status == "cancelled":
                row.status = "registered"
            row.registration_time = now()
            row.slot_release_at = None
            row.reject_reason = None
        else:
            row = Registration(activity_id=activity.id, user_id=request.current_user_id, status="registered")
            session.add(row)
            session.flush()

        session.flush()
        refresh_participants(session, activity)
        return success(
            {
                "registration_id": row.id,
                "status": row.status,
                "remaining_slots": remaining_slots(session, activity),
            },
            message="报名成功",
        )


@bp.delete("/registrations/<int:activity_id>")
@role_required("user")
def cancel_registration(activity_id):
    with db_session() as session:
        activity = session.get(Activity, activity_id)
        if not activity:
            raise ApiError("活动不存在", code=404, status_code=404)
        if now() > activity.cancel_deadline:
            raise ApiError("取消报名已截止")
        row = (
            session.query(Registration)
            .filter(Registration.activity_id == activity_id, Registration.user_id == request.current_user_id)
            .first()
        )
        if not row or row.status not in ACTIVE_STATUSES:
            raise ApiError("你尚未报名该活动")

        release_time = now() + timedelta(minutes=2)
        row.status = "cancelled"
        row.slot_release_at = release_time
        session.flush()
        refresh_participants(session, activity)
        return success({"release_time": dt(release_time)}, message="取消报名成功，名额将在 2 分钟后释放")


@bp.get("/registrations/my")
@role_required("user")
def my_registrations():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    with db_session() as session:
        query = (
            session.query(Registration)
            .join(Activity, Registration.activity_id == Activity.id)
            .filter(Registration.user_id == request.current_user_id)
            .order_by(Registration.registration_time.desc())
        )
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        data = []
        for row in rows:
            checkin = (
                session.query(Checkin)
                .filter(Checkin.activity_id == row.activity_id, Checkin.user_id == row.user_id)
                .first()
            )
            data.append(
                {
                    "registration_id": row.id,
                    "activity_id": row.activity_id,
                    "activity_name": row.activity.name,
                    "start_time": dt(row.activity.start_time),
                    "end_time": dt(row.activity.end_time),
                    "location": row.activity.location,
                    "registration_time": dt(row.registration_time),
                    "status": row.status,
                    "checkin_status": "checked" if checkin else "not_checked",
                    "checkin_time": dt(checkin.checkin_time) if checkin else None,
                }
            )
        return success({"total": total, "page": page, "page_size": page_size, "list": data})


def ensure_activity_owner(session, activity_id):
    activity = session.get(Activity, activity_id)
    if not activity:
        raise ApiError("活动不存在", code=404, status_code=404)
    if request.current_role == "organizer" and activity.organizer_id != request.current_user_id:
        raise ApiError("无权管理该活动", code=403, status_code=403)
    return activity


def filtered_registration_query(session, activity_id):
    query = session.query(Registration).join(User, Registration.user_id == User.id).filter(Registration.activity_id == activity_id)
    for field in ["gender", "college", "grade", "major"]:
        value = request.args.get(field)
        if value:
            query = query.filter(getattr(User, field) == value)
    status = request.args.get("status")
    if status:
        query = query.filter(Registration.status == status)
    return query


def stats_for(rows, activity):
    active_rows = [row for row in rows if row.status in ACTIVE_STATUSES]
    return {
        "total_registered": len(active_rows),
        "remaining_slots": max(activity.max_participants - len(active_rows), 0),
        "by_gender": dict(Counter(row.user.gender for row in active_rows)),
        "by_college": dict(Counter(row.user.college for row in active_rows)),
        "by_grade": dict(Counter(row.user.grade for row in active_rows)),
        "by_major": dict(Counter(row.user.major for row in active_rows)),
    }


@bp.get("/activities/<int:activity_id>/registrations")
@role_required("organizer", "admin")
def activity_registrations(activity_id):
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    with db_session() as session:
        activity = ensure_activity_owner(session, activity_id)
        query = filtered_registration_query(session, activity_id)
        total = query.count()
        all_rows = query.all()
        rows = query.order_by(Registration.registration_time.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return success(
            {
                "total": total,
                "statistics": stats_for(all_rows, activity),
                "list": [
                    {
                        "registration_id": row.id,
                        "user_id": row.user.id,
                        "student_id": row.user.student_id,
                        "username": row.user.username,
                        "gender": row.user.gender,
                        "college": row.user.college,
                        "major": row.user.major,
                        "grade": row.user.grade,
                        "phone": row.user.phone,
                        "registration_time": dt(row.registration_time),
                        "status": row.status,
                        "reject_reason": row.reject_reason,
                        "checkin_status": "checked"
                        if session.query(Checkin).filter(Checkin.activity_id == activity_id, Checkin.user_id == row.user_id).first()
                        else "not_checked",
                    }
                    for row in rows
                ],
            }
        )


@bp.put("/activities/<int:activity_id>/registrations/<int:user_id>/reject")
@role_required("organizer")
def reject_registration(activity_id, user_id):
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise ApiError("请填写拒绝原因")
    with db_session() as session:
        activity = ensure_activity_owner(session, activity_id)
        row = session.query(Registration).filter(Registration.activity_id == activity_id, Registration.user_id == user_id).first()
        if not row or row.status not in ACTIVE_STATUSES:
            raise ApiError("该用户没有有效报名记录")
        row.reject_count += 1
        row.last_reject_time = now()
        row.reject_reason = reason
        row.status = "blocked" if row.reject_count >= 2 else "rejected"
        session.flush()
        refresh_participants(session, activity)
        return success({"new_status": row.status, "reject_count": row.reject_count}, message="已拒绝该用户报名")


@bp.get("/activities/<int:activity_id>/registration-stats")
@role_required("organizer", "admin")
def registration_stats(activity_id):
    with db_session() as session:
        activity = ensure_activity_owner(session, activity_id)
        rows = session.query(Registration).filter(Registration.activity_id == activity_id).all()
        return success(stats_for(rows, activity))
