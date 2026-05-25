from datetime import datetime

from flask import Blueprint, request

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from app.services.notification_service import create_notification
from models import Activity, ActivityRevision, Category, Organizer, Registration

bp = Blueprint("admin_activities", __name__, url_prefix="/admin/activities")

ACTIVE_STATUSES = ("registered", "re_registered")
REVIEWABLE_STATUSES = ("pending", "edit_pending")
ALL_STATUSES = ("draft", "pending", "rejected", "edit_pending", "open", "ongoing", "ended", "removed")


def list_statuses(value):
    if not value:
        return None
    parts = [item.strip() for item in value.split(",") if item.strip()]
    return parts or None


def category_map(session):
    return {row.id: row for row in session.query(Category).all()}


def category_path(category_id, by_id):
    names = []
    current = by_id.get(category_id)
    while current:
        names.append(current.name)
        current = by_id.get(current.parent_id)
    return " > ".join(reversed(names))


def get_revision(session, activity_id):
    return session.query(ActivityRevision).filter(ActivityRevision.activity_id == activity_id).first()


def apply_revision_to_activity(activity, revision):
    activity.name = revision.name
    activity.category_id = revision.category_id
    activity.start_time = revision.start_time
    activity.end_time = revision.end_time
    activity.campus = revision.campus
    activity.location = revision.location
    activity.max_participants = revision.max_participants
    activity.registration_deadline = revision.registration_deadline
    activity.cancel_deadline = revision.cancel_deadline
    activity.description = revision.description


def compute_activity_status(activity):
    now = datetime.utcnow()
    if activity.end_time and now > activity.end_time:
        return "ended"
    if activity.start_time and activity.start_time <= now <= activity.end_time:
        return "ongoing"
    return "open"


@bp.get("")
@role_required("admin")
def list_review_activities():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)

    with db_session() as session:
        query = session.query(Activity, Organizer).join(Organizer, Activity.organizer_id == Organizer.id)

        statuses = list_statuses(request.args.get("status"))
        if statuses:
            if "end" in statuses:
                statuses = [status for status in statuses if status != "end"]
                statuses.extend([status for status in ALL_STATUSES if status not in REVIEWABLE_STATUSES])
                statuses = list(dict.fromkeys(statuses))
            query = query.filter(Activity.status.in_(statuses))

        if keyword := str(request.args.get("keyword") or "").strip():
            query = query.filter(Activity.name.contains(keyword))
        if organizer_id := request.args.get("organizer_id"):
            try:
                query = query.filter(Activity.organizer_id == int(organizer_id))
            except ValueError as exc:
                raise ApiError("组织者ID无效") from exc
        if category_id := request.args.get("categories_id") or request.args.get("category_id"):
            try:
                query = query.filter(Activity.category_id == int(category_id))
            except ValueError as exc:
                raise ApiError("分类ID无效") from exc
        if start_date := request.args.get("start_date"):
            try:
                start_time = datetime.strptime(str(start_date), "%Y-%m-%d")
            except ValueError as exc:
                raise ApiError("start_date无效") from exc
            query = query.filter(Activity.start_time >= start_time)

        total = query.count()
        rows = (
            query.order_by(Activity.start_time.desc(), Activity.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        categories = category_map(session)

        items = []
        for activity, organizer in rows:
            revision = get_revision(session, activity.id) if activity.status == "edit_pending" else None
            source = revision or activity
            category = categories.get(source.category_id) if source.category_id else None
            items.append(
                {
                    "activity_id": activity.id,
                    "name": source.name,
                    "organizer_id": organizer.id,
                    "organizer_name": organizer.org_name,
                    "start_time": dt(source.start_time),
                    "category_name": category.name if category else None,
                    "category_path": category_path(source.category_id, categories) if category else None,
                    "status": activity.status,
                }
            )

        return success({"total": total, "page": page, "page_size": page_size, "list": items})


@bp.put("/<int:activity_id>/review")
@role_required("admin")
def review_activity(activity_id):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip()
    reject_reason = str(data.get("reject_reason") or "").strip()

    if action not in ("approve", "reject"):
        raise ApiError("action无效")
    if action == "reject" and not reject_reason:
        raise ApiError("reject_reason必填")

    with db_session() as session:
        activity = session.get(Activity, activity_id)
        if not activity or activity.status == "removed":
            raise ApiError("活动不存在", code=404, status_code=404)
        if activity.status not in REVIEWABLE_STATUSES:
            raise ApiError("当前活动状态不可审核")

        if action == "approve":
            if activity.status == "edit_pending":
                revision = get_revision(session, activity.id)
                if revision:
                    apply_revision_to_activity(activity, revision)
                    session.delete(revision)
                activity.status = compute_activity_status(activity)
            else:
                activity.status = "open"
            activity.reject_reason = None
            message = "审核通过"
            new_status = activity.status
            notice_content = f"Your activity {activity.name} was approved."
        else:
            if activity.status == "edit_pending":
                revision = get_revision(session, activity.id)
                if revision:
                    session.delete(revision)
                activity.status = compute_activity_status(activity)
                activity.reject_reason = reject_reason
                message = "审核拒绝"
                new_status = activity.status
            else:
                activity.status = "rejected"
                activity.reject_reason = reject_reason
                message = "审核拒绝"
                new_status = "rejected"
            notice_content = f"Your activity {activity.name} was rejected. Reason: {reject_reason}"

        create_notification(
            session,
            "organizer",
            activity.organizer_id,
            "Activity Review Result",
            notice_content,
            "activity_audit_result",
            activity.id,
        )
        return success({"activity_id": activity.id, "new_status": new_status}, message=message)


@bp.put("/<int:activity_id>/remove")
@role_required("admin")
def remove_activity(activity_id):
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise ApiError("请填写下架原因")

    with db_session() as session:
        activity = session.get(Activity, activity_id)
        if not activity or activity.status == "removed":
            raise ApiError("活动不存在", code=404, status_code=404)

        activity.status = "removed"
        activity.reject_reason = reason
        session.flush()

        create_notification(
            session,
            "organizer",
            activity.organizer_id,
            "Activity Removed",
            f"Your activity {activity.name} was removed. Reason: {reason}",
            "activity_audit_result",
            activity.id,
        )

        rows = (
            session.query(Registration)
            .filter(Registration.activity_id == activity_id, Registration.status.in_(ACTIVE_STATUSES))
            .all()
        )
        for row in rows:
            create_notification(
                session,
                "user",
                row.user_id,
                "Activity Removed",
                f"The activity {activity.name} was removed. Reason: {reason}",
                "activity_audit_result",
                activity.id,
            )

        return success(None, message="活动已下架，已通知发布者和所有报名用户")
