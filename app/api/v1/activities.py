from datetime import datetime

from flask import Blueprint, request

from app.common.auth import role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from app.services.notification_service import create_notification
from models import Activity, Category, Checkin, Organizer, Registration

bp = Blueprint("activities", __name__, url_prefix="")


def parse_datetime(value, field):
    if not value:
        raise ApiError(f"{field} is required")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ApiError(f"{field} must use YYYY-MM-DD HH:MM:SS")


def category_path(session, category):
    if not category:
        return None
    if category.parent_id:
        parent = session.get(Category, category.parent_id)
        if parent:
            return f"{parent.name} > {category.name}"
    return category.name


def activity_list_item(session, activity, include_status=True):
    item = {
        "activity_id": activity.id,
        "name": activity.name,
        "start_time": dt(activity.start_time),
        "category_name": activity.category.name if activity.category else None,
        "category_path": category_path(session, activity.category),
        "location": activity.location,
        "campus": activity.campus,
        "current_participants": activity.current_participants,
        "max_participants": activity.max_participants,
    }
    if include_status:
        item["status"] = activity.status
    return item


def load_activity_for_organizer(session, activity_id):
    activity = session.get(Activity, activity_id)
    if not activity:
        raise ApiError("活动不存在", code=404, status_code=404)
    if activity.organizer_id != request.current_user_id:
        raise ApiError("无权管理该活动", code=403, status_code=403)
    return activity


@bp.post("/organizer/activities")
@role_required("organizer")
def create_activity():
    data = request.get_json(silent=True) or {}
    required = ["name", "category_id", "start_time", "end_time", "campus", "location", "max_participants", "registration_deadline", "cancel_deadline", "description"]
    missing = [field for field in required if data.get(field) in (None, "")]
    if missing:
        raise ApiError(f"Missing fields: {', '.join(missing)}")
    max_participants = int(data["max_participants"])
    if max_participants < 1:
        raise ApiError("max_participants must be at least 1")

    with db_session() as session:
        organizer = session.get(Organizer, request.current_user_id)
        if not organizer or organizer.status != "approved":
            raise ApiError("组织者账号未审核通过，暂不能创建活动", code=403, status_code=403)
        activity = Activity(
            organizer_id=request.current_user_id,
            category_id=int(data["category_id"]),
            name=str(data["name"]).strip(),
            start_time=parse_datetime(data["start_time"], "start_time"),
            end_time=parse_datetime(data["end_time"], "end_time"),
            campus=str(data["campus"]).strip(),
            location=str(data["location"]).strip(),
            max_participants=max_participants,
            current_participants=0,
            registration_deadline=parse_datetime(data["registration_deadline"], "registration_deadline"),
            cancel_deadline=parse_datetime(data["cancel_deadline"], "cancel_deadline"),
            description=str(data["description"]).strip(),
            status="draft",
        )
        session.add(activity)
        session.flush()
        return success({"activity_id": activity.id, "status": activity.status}, message="活动创建成功")


@bp.post("/organizer/activities/<int:activity_id>/submit")
@role_required("organizer")
def submit_activity(activity_id):
    with db_session() as session:
        activity = load_activity_for_organizer(session, activity_id)
        activity.status = "edit_pending" if activity.status == "open" else "pending"
        return success({"activity_id": activity.id, "status": activity.status}, message="已提交审核")


@bp.get("/activities")
def list_activities():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    with db_session() as session:
        query = session.query(Activity).filter(Activity.status.in_(("open", "ongoing")))
        keyword = request.args.get("keyword") or request.args.get("name")
        if keyword:
            query = query.filter(Activity.name.like(f"%{keyword}%"))
        category_id = request.args.get("category_id")
        if category_id:
            query = query.filter(Activity.category_id == int(category_id))
        campus = request.args.get("campus")
        if campus:
            query = query.filter(Activity.campus == campus)
        total = query.count()
        rows = query.order_by(Activity.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return success({"total": total, "page": page, "page_size": page_size, "list": [activity_list_item(session, row, include_status=False) for row in rows]})


@bp.get("/activities/<int:activity_id>")
def activity_detail(activity_id):
    with db_session() as session:
        activity = session.get(Activity, activity_id)
        if not activity:
            raise ApiError("活动不存在", code=404, status_code=404)
        registration = None
        checkin = None
        if getattr(request, "current_role", None) == "user":
            registration = session.query(Registration).filter(Registration.activity_id == activity.id, Registration.user_id == request.current_user_id).first()
            checkin = session.query(Checkin).filter(Checkin.activity_id == activity.id, Checkin.user_id == request.current_user_id).first()
        return success(
            {
                "activity_id": activity.id,
                "organizer_id": activity.organizer_id,
                "organizer_name": activity.organizer.org_name if activity.organizer else None,
                "name": activity.name,
                "category_id": activity.category_id,
                "category_name": activity.category.name if activity.category else None,
                "category_path": category_path(session, activity.category),
                "start_time": dt(activity.start_time),
                "end_time": dt(activity.end_time),
                "campus": activity.campus,
                "location": activity.location,
                "max_participants": activity.max_participants,
                "current_participants": activity.current_participants,
                "registration_deadline": dt(activity.registration_deadline),
                "cancel_deadline": dt(activity.cancel_deadline),
                "description": activity.description,
                "status": activity.status,
                "is_registered": bool(registration and registration.status in ("registered", "re_registered")),
                "registration_status": registration.status if registration else None,
                "check_status": bool(checkin),
            }
        )


@bp.put("/organizer/activities/<int:activity_id>")
@role_required("organizer")
def update_activity(activity_id):
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        activity = load_activity_for_organizer(session, activity_id)
        for field in ["name", "campus", "location", "description"]:
            if field in data:
                setattr(activity, field, str(data[field]).strip())
        for field in ["category_id", "max_participants"]:
            if field in data:
                setattr(activity, field, int(data[field]))
        for field in ["start_time", "end_time", "registration_deadline", "cancel_deadline"]:
            if field in data:
                setattr(activity, field, parse_datetime(data[field], field))
        activity.status = "edit_pending" if activity.status == "open" else "draft"
        return success({"activity_id": activity.id, "status": activity.status}, message="活动更新成功")


@bp.delete("/organizer/activities/<int:activity_id>")
@role_required("organizer")
def delete_activity(activity_id):
    with db_session() as session:
        activity = load_activity_for_organizer(session, activity_id)
        rows = session.query(Registration).filter(Registration.activity_id == activity.id).all()
        for row in rows:
            create_notification(session, "user", row.user_id, "Activity Deleted", f"Activity {activity.name} has been deleted.", "activity_change", activity.id)
        session.delete(activity)
        return success(None, message="活动已删除，已通知所有报名用户")


@bp.get("/organizer/activities")
@role_required("organizer")
def my_activities():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    with db_session() as session:
        query = session.query(Activity).filter(Activity.organizer_id == request.current_user_id)
        total = query.count()
        rows = query.order_by(Activity.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return success({"total": total, "page": page, "page_size": page_size, "list": [activity_list_item(session, row) for row in rows]})
