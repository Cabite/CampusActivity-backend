from datetime import datetime, timedelta

from flask import Blueprint, request

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from models import Announcement, Notification

bp = Blueprint("notifications", __name__, url_prefix="")


def parse_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ApiError("Invalid datetime format. Use YYYY-MM-DD HH:MM:SS.")


def serialize_notification(row):
    return {
        "notification_id": row.id,
        "title": row.title,
        "content": row.content,
        "type": row.type,
        "related_id": row.related_id,
        "is_read": bool(row.is_read),
        "created_at": dt(row.created_at),
    }


@bp.get("/notifications")
@role_required("user", "organizer", "admin")
def list_notifications():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    only_unread = request.args.get("unread") in ("1", "true", "True")

    with db_session() as session:
        query = session.query(Notification).filter(
            Notification.receiver_type == request.current_role,
            Notification.receiver_id == request.current_user_id,
        )
        if only_unread:
            query = query.filter(Notification.is_read.is_(False))
        unread_count = (
            session.query(Notification)
            .filter(
                Notification.receiver_type == request.current_role,
                Notification.receiver_id == request.current_user_id,
                Notification.is_read.is_(False),
            )
            .count()
        )
        total = query.count()
        rows = (
            query.order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return success(
            {
                "total": total,
                "page": page,
                "page_size": page_size,
                "unread_count": unread_count,
                "list": [serialize_notification(row) for row in rows],
            }
        )


@bp.put("/notifications/<int:notification_id>/read")
@role_required("user", "organizer", "admin")
def mark_notification_read(notification_id):
    with db_session() as session:
        row = session.get(Notification, notification_id)
        if not row or row.receiver_type != request.current_role or row.receiver_id != request.current_user_id:
            raise ApiError("Notification not found", code=404, status_code=404)
        row.is_read = True
        return success(None, message="已标记为已读")


@bp.put("/notifications/read-all")
@role_required("user", "organizer", "admin")
def mark_all_notifications_read():
    with db_session() as session:
        session.query(Notification).filter(
            Notification.receiver_type == request.current_role,
            Notification.receiver_id == request.current_user_id,
            Notification.is_read.is_(False),
        ).update({"is_read": True}, synchronize_session=False)
        return success(None, message="全部已标记为已读")


@bp.post("/admin/announcements")
@role_required("admin")
def create_announcement():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    content = str(data.get("content") or "").strip()
    if not title:
        raise ApiError("Announcement title is required")
    if not content:
        raise ApiError("Announcement content is required")
    if len(title) > 50:
        raise ApiError("Announcement title must be 50 characters or fewer")

    start_time = parse_datetime(data.get("start_time")) or datetime.utcnow()
    end_time = parse_datetime(data.get("expires_at") or data.get("end_time")) or (start_time + timedelta(days=30))
    if end_time <= start_time:
        raise ApiError("Announcement end time must be later than start time")

    with db_session() as session:
        row = Announcement(
            admin_id=request.current_user_id,
            title=title,
            content=content,
            start_time=start_time,
            end_time=end_time,
        )
        session.add(row)
        session.flush()
        return success({"announcement_id": row.id}, message="公告发布成功")


@bp.get("/announcements")
def list_announcements():
    current_time = datetime.utcnow()
    with db_session() as session:
        rows = (
            session.query(Announcement)
            .filter(Announcement.start_time <= current_time, Announcement.end_time >= current_time)
            .order_by(Announcement.created_at.desc(), Announcement.id.desc())
            .all()
        )
        return success(
            [
                {
                    "announcement_id": row.id,
                    "title": row.title,
                    "content": row.content,
                    "created_at": dt(row.created_at),
                    "expires_at": dt(row.end_time),
                }
                for row in rows
            ]
        )
