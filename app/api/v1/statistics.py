from datetime import datetime, timedelta

from flask import Blueprint, request
from sqlalchemy import func

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from models import Activity, Admin, Category, Checkin, Organizer, Registration, User

bp = Blueprint("statistics", __name__, url_prefix="")

ACTIVE_REGISTRATION_STATUSES = ("registered", "re_registered")
PLATFORM_ACTIVITY_STATUSES = ("pending", "open", "edit_pending", "ongoing", "ended")
ACHIEVEMENT_LEVELS = [
    {"title": "初级探索者", "required_count": 5},
    {"title": "中级探索者", "required_count": 20},
    {"title": "高级探索者", "required_count": 30},
]


def parse_page_args():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError) as exc:
        raise ApiError("分页参数无效") from exc
    return page, page_size


def utcnow():
    return datetime.utcnow()


def parse_period(value):
    period = str(value or "all").strip().lower()
    if period not in ("week", "month", "all"):
        raise ApiError("period无效")
    if period == "week":
        return utcnow() - timedelta(days=7)
    if period == "month":
        return utcnow() - timedelta(days=30)
    return None


def parse_scope(scope, filter_value):
    scope_value = str(scope or "global").strip().lower()
    if scope_value not in ("global", "college", "grade"):
        raise ApiError("scope无效")
    if scope_value != "global" and not str(filter_value or "").strip():
        raise ApiError("scope不为global时需要filter_value")
    return scope_value


def resolve_scope_from_args():
    college = str(request.args.get("college") or "").strip()
    grade = str(request.args.get("grade") or "").strip()
    if college:
        return "college", college
    if grade:
        return "grade", grade
    filter_value = str(request.args.get("filter_value") or "").strip()
    scope_value = parse_scope(request.args.get("scope"), filter_value)
    if scope_value == "global":
        return scope_value, ""
    return scope_value, filter_value


@bp.get("/admin/statistics")
@role_required("admin")
def admin_statistics():
    with db_session() as session:
        activity_query = session.query(Activity).filter(Activity.status.in_(PLATFORM_ACTIVITY_STATUSES))
        activities_total = activity_query.count()
        status_counts = (
            session.query(Activity.status, func.count(Activity.id))
            .filter(Activity.status.in_(PLATFORM_ACTIVITY_STATUSES))
            .group_by(Activity.status)
            .all()
        )
        by_statuss = {status: count for status, count in status_counts}
        for status in PLATFORM_ACTIVITY_STATUSES:
            by_statuss.setdefault(status, 0)

        category_counts = (
            session.query(Category.name, func.count(Activity.id))
            .join(Activity, Activity.category_id == Category.id)
            .filter(Activity.status.in_(PLATFORM_ACTIVITY_STATUSES))
            .group_by(Category.name)
            .all()
        )
        by_categories = {name: count for name, count in category_counts}

        student_count = session.query(User).filter(User.status != "deleted").count()
        organizer_count = session.query(Organizer).filter(Organizer.status != "deleted").count()
        admin_count = session.query(Admin).filter(Admin.status != "deleted").count()

        total_registrations = (
            session.query(Registration)
            .filter(Registration.status.in_(ACTIVE_REGISTRATION_STATUSES))
            .count()
        )
        total_checkins = session.query(Checkin).count()
        if total_registrations:
            rate = (total_checkins / total_registrations) * 100
            average_checkin_rate = f"{rate:.1f}%"
        else:
            average_checkin_rate = "0.0%"

        return success(
            {
                "activities": {
                    "total": activities_total,
                    "by_statuss": by_statuss,
                    "by_categories": by_categories,
                },
                "user": {
                    "total": student_count + organizer_count + admin_count,
                    "student": student_count,
                    "organize": organizer_count,
                    "admin": admin_count,
                },
                "total_participation_count": total_checkins,
                "average_checkin_rate": average_checkin_rate,
            }
        )


@bp.get("/statistics/user-ranking")
@role_required("user", "organizer", "admin")
def user_ranking():
    period_start = parse_period(request.args.get("period"))
    scope, filter_value = resolve_scope_from_args()
    page, page_size = parse_page_args()

    with db_session() as session:
        user_query = session.query(User).filter(User.status != "deleted")
        if scope == "college":
            user_query = user_query.filter(User.college == filter_value)
        elif scope == "grade":
            user_query = user_query.filter(User.grade == filter_value)

        registration_query = session.query(Registration.user_id, func.count(Registration.id).label("registration_count"))
        registration_query = registration_query.filter(Registration.status.in_(ACTIVE_REGISTRATION_STATUSES))
        if period_start:
            registration_query = registration_query.filter(Registration.registration_time >= period_start)
        registration_query = registration_query.group_by(Registration.user_id)
        registration_subq = registration_query.subquery()

        checkin_query = session.query(Checkin.user_id, func.count(Checkin.id).label("effective_count"))
        if period_start:
            checkin_query = checkin_query.filter(Checkin.checkin_time >= period_start)
        checkin_query = checkin_query.group_by(Checkin.user_id)
        checkin_subq = checkin_query.subquery()

        query = (
            user_query.outerjoin(registration_subq, registration_subq.c.user_id == User.id)
            .outerjoin(checkin_subq, checkin_subq.c.user_id == User.id)
            .add_columns(
                func.coalesce(registration_subq.c.registration_count, 0).label("registration_count"),
                func.coalesce(checkin_subq.c.effective_count, 0).label("effective_participation_count"),
            )
        )

        total = query.count()
        rows = (
            query.order_by(
                func.coalesce(checkin_subq.c.effective_count, 0).desc(),
                func.coalesce(registration_subq.c.registration_count, 0).desc(),
                User.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        data = []
        for index, (user, registration_count, effective_count) in enumerate(rows):
            data.append(
                {
                    "rank": (page - 1) * page_size + index + 1,
                    "user_id": user.id,
                    "student_id": user.student_id,
                    "college": user.college,
                    "grade": user.grade,
                    "registration_count": int(registration_count or 0),
                    "effective_participation_count": int(effective_count or 0),
                }
            )

        return success({"total": total, "list": data})


@bp.get("/leaderboard")
def leaderboard():
    return user_ranking_data(require_auth=False)


def user_ranking_data(require_auth=True):
    period_start = parse_period(request.args.get("period"))
    scope, filter_value = resolve_scope_from_args()
    page, page_size = parse_page_args()

    with db_session() as session:
        user_query = session.query(User).filter(User.status != "deleted")
        if scope == "college":
            user_query = user_query.filter(User.college == filter_value)
        elif scope == "grade":
            user_query = user_query.filter(User.grade == filter_value)

        registration_query = session.query(Registration.user_id, func.count(Registration.id).label("registration_count"))
        registration_query = registration_query.filter(Registration.status.in_(ACTIVE_REGISTRATION_STATUSES))
        if period_start:
            registration_query = registration_query.filter(Registration.registration_time >= period_start)
        registration_query = registration_query.group_by(Registration.user_id)
        registration_subq = registration_query.subquery()

        checkin_query = session.query(Checkin.user_id, func.count(Checkin.id).label("effective_count"))
        if period_start:
            checkin_query = checkin_query.filter(Checkin.checkin_time >= period_start)
        checkin_query = checkin_query.group_by(Checkin.user_id)
        checkin_subq = checkin_query.subquery()

        query = (
            user_query.outerjoin(registration_subq, registration_subq.c.user_id == User.id)
            .outerjoin(checkin_subq, checkin_subq.c.user_id == User.id)
            .add_columns(
                func.coalesce(registration_subq.c.registration_count, 0).label("registration_count"),
                func.coalesce(checkin_subq.c.effective_count, 0).label("effective_participation_count"),
            )
        )

        total = query.count()
        rows = (
            query.order_by(
                func.coalesce(checkin_subq.c.effective_count, 0).desc(),
                func.coalesce(registration_subq.c.registration_count, 0).desc(),
                User.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        data = []
        for index, (user, registration_count, effective_count) in enumerate(rows):
            data.append(
                {
                    "rank": (page - 1) * page_size + index + 1,
                    "user_id": user.id,
                    "student_id": user.student_id,
                    "college": user.college,
                    "grade": user.grade,
                    "registration_count": int(registration_count or 0),
                    "effective_participation_count": int(effective_count or 0),
                }
            )

        return success({"total": total, "list": data})


@bp.get("/user/achievement")
@role_required("user")
def user_achievement():
    with db_session() as session:
        user = session.get(User, request.current_user_id)
        if not user or user.status == "deleted":
            raise ApiError("用户不存在", code=404, status_code=404)

        checkins = (
            session.query(Checkin)
            .filter(Checkin.user_id == user.id)
            .order_by(Checkin.checkin_time.asc())
            .all()
        )
        effective_count = len(checkins)

        achievements = []
        current_title = "无"
        next_title = None
        next_required = None

        for level in ACHIEVEMENT_LEVELS:
            required = level["required_count"]
            unlocked = effective_count >= required
            unlocked_at = dt(checkins[required - 1].checkin_time) if unlocked else None
            if unlocked:
                current_title = level["title"]
            elif next_title is None:
                next_title = level["title"]
                next_required = required

            achievements.append(
                {
                    "title": level["title"],
                    "required_count": required,
                    "unlocked_at": unlocked_at,
                    "unlocked": unlocked,
                }
            )

        return success(
            {
                "current_title": current_title,
                "effective_participation_count": effective_count,
                "next_title": next_title,
                "next_required": next_required,
                "achievements": achievements,
            }
        )
