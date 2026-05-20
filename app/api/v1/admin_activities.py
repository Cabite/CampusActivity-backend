from flask import Blueprint, request

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from app.services.notification_service import create_notification
from models import Activity, Organizer, Registration

bp = Blueprint("admin_activities", __name__, url_prefix="/admin/activities")

ACTIVE_STATUSES = ("registered", "re_registered")
REVIEWABLE_STATUSES = ("pending", "edit_pending")


def list_statuses(value):
    if not value:
        return None
    parts = [item.strip() for item in value.split(",") if item.strip()]
    return parts or None


@bp.get("")
@role_required("admin")
def list_review_activities():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)

    with db_session() as session:
        query = session.query(Activity, Organizer).join(Organizer, Activity.organizer_id == Organizer.id)

        statuses = list_statuses(request.args.get("status"))
        if statuses:
            query = query.filter(Activity.status.in_(statuses))
        else:
            query = query.filter(Activity.status.in_(REVIEWABLE_STATUSES))

        if keyword := str(request.args.get("keyword") or "").strip():
            query = query.filter(Activity.name.contains(keyword))
        if organizer_id := request.args.get("organizer_id"):
            try:
                query = query.filter(Activity.organizer_id == int(organizer_id))
            except ValueError as exc:
                raise ApiError("组织者ID无效") from exc

        total = query.count()
        rows = (
            query.order_by(Activity.start_time.desc(), Activity.id.desc())
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
                        "activity_id": activity.id,
                        "name": activity.name,
                        "organizer_id": organizer.id,
                        "organizer_name": organizer.org_name,
                        "start_time": dt(activity.start_time),
                        "status": activity.status,
                        "submitted_at": dt(activity.start_time),
                    }
                    for activity, organizer in rows
                ],
            }
        )


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
            activity.status = "open"
            activity.reject_reason = None
            message = "审核通过"
            new_status = "open"
            notice_content = f"Your activity {activity.name} was approved."
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
