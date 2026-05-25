from datetime import datetime

from flask import Blueprint, request

from app.common.auth import decode_token, role_required
from app.common.database import db_session
from app.common.errors import ApiError
from app.common.response import success
from app.common.serializers import dt
from app.services.notification_service import create_notification
from models import Activity, ActivityRevision, Category, Checkin, Organizer, Registration

bp = Blueprint("activities", __name__, url_prefix="")

ACTIVE_STATUSES = ("registered", "re_registered")
EDITABLE_DIRECT_STATUSES = ("draft", "pending", "rejected")


def parse_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ApiError("Invalid datetime format. Use YYYY-MM-DD HH:MM:SS.")


def require_fields(data, fields):
    missing = [field for field in fields if not str(data.get(field, "")).strip()]
    if missing:
        raise ApiError(f"缺少必填字段：{', '.join(missing)}")


def list_statuses(value):
    if not value:
        return None
    parts = [item.strip() for item in str(value).split(",") if item.strip()]
    return parts or None


def optional_identity():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, None
    payload = decode_token(header.replace("Bearer ", "", 1).strip())
    return payload.get("role"), payload.get("user_id")


def category_map(session):
    return {row.id: row for row in session.query(Category).all()}


def category_path(category_id, by_id):
    names = []
    current = by_id.get(category_id)
    while current:
        names.append(current.name)
        current = by_id.get(current.parent_id)
    return " > ".join(reversed(names))


def normalized_payload(data):
    require_fields(
        data,
        [
            "name",
            "category_id",
            "start_time",
            "end_time",
            "campus",
            "location",
            "max_participants",
            "registration_deadline",
            "cancel_deadline",
            "description",
        ],
    )

    try:
        category_id = int(data["category_id"])
    except (TypeError, ValueError) as exc:
        raise ApiError("分类ID无效") from exc

    try:
        max_participants = int(data["max_participants"])
    except (TypeError, ValueError) as exc:
        raise ApiError("人数上限无效") from exc

    if max_participants <= 0:
        raise ApiError("人数上限必须大于0")

    start_time = parse_datetime(data.get("start_time"))
    end_time = parse_datetime(data.get("end_time"))
    registration_deadline = parse_datetime(data.get("registration_deadline"))
    cancel_deadline = parse_datetime(data.get("cancel_deadline"))
    if not start_time or not end_time:
        raise ApiError("活动时间不能为空")
    if end_time <= start_time:
        raise ApiError("结束时间必须晚于开始时间")
    if registration_deadline and registration_deadline > start_time:
        raise ApiError("报名截止时间必须早于活动开始")
    if cancel_deadline and cancel_deadline > start_time:
        raise ApiError("取消截止时间必须早于活动开始")
    if registration_deadline and cancel_deadline and cancel_deadline > registration_deadline:
        raise ApiError("取消截止时间必须早于报名截止时间")

    return {
        "name": str(data["name"]).strip(),
        "category_id": category_id,
        "start_time": start_time,
        "end_time": end_time,
        "campus": str(data["campus"]).strip(),
        "location": str(data["location"]).strip(),
        "max_participants": max_participants,
        "registration_deadline": registration_deadline,
        "cancel_deadline": cancel_deadline,
        "description": str(data["description"]).strip(),
    }


def apply_activity_fields(activity, payload):
    activity.name = payload["name"]
    activity.category_id = payload["category_id"]
    activity.start_time = payload["start_time"]
    activity.end_time = payload["end_time"]
    activity.campus = payload["campus"]
    activity.location = payload["location"]
    activity.max_participants = payload["max_participants"]
    activity.registration_deadline = payload["registration_deadline"]
    activity.cancel_deadline = payload["cancel_deadline"]
    activity.description = payload["description"]


def apply_revision_fields(revision, payload):
    revision.name = payload["name"]
    revision.category_id = payload["category_id"]
    revision.start_time = payload["start_time"]
    revision.end_time = payload["end_time"]
    revision.campus = payload["campus"]
    revision.location = payload["location"]
    revision.max_participants = payload["max_participants"]
    revision.registration_deadline = payload["registration_deadline"]
    revision.cancel_deadline = payload["cancel_deadline"]
    revision.description = payload["description"]


def get_revision(session, activity_id):
    return session.query(ActivityRevision).filter(ActivityRevision.activity_id == activity_id).first()


def activity_list_item(row, include_status):
    return {
        "activity_id": row.activity_id if hasattr(row, "activity_id") else row.id,
        "name": row.name,
        "start_time": dt(row.start_time),
        "category_id": row.category_id,
        "location": row.location,
        "campus": row.campus,
        "max_participants": getattr(row, "max_participants", None),
        "status": row.status if include_status and hasattr(row, "status") else None,
    }


def enrich_activity_item(item, categories, activity, include_status):
    category = categories.get(item["category_id"]) if item.get("category_id") else None
    item["category_name"] = category.name if category else None
    item["category_path"] = category_path(item["category_id"], categories) if category else None
    item["current_participants"] = activity.current_participants
    if include_status:
        item["status"] = activity.status
    else:
        item.pop("status", None)
    item.pop("category_id", None)
    return item


def load_activity_for_organizer(session, activity_id):
    activity = session.get(Activity, activity_id)
    if not activity or activity.status == "removed":
        raise ApiError("活动不存在", code=404, status_code=404)
    if activity.organizer_id != request.current_user_id:
        raise ApiError("无权管理该活动", code=403, status_code=403)
    return activity


@bp.post("/organizer/activities")
@bp.post("/activities")
@role_required("organizer")
def create_activity():
    data = request.get_json(silent=True) or {}
    payload = normalized_payload(data)

    with db_session() as session:
        organizer = session.get(Organizer, request.current_user_id)
        if not organizer or organizer.status != "approved":
            raise ApiError("组织者账号未审核通过，暂不能创建活动", code=403, status_code=403)
        if not session.get(Category, payload["category_id"]):
            raise ApiError("活动分类不存在", code=404, status_code=404)

        activity = Activity(
            organizer_id=request.current_user_id,
            category_id=payload["category_id"],
            name=payload["name"],
            start_time=payload["start_time"],
            end_time=payload["end_time"],
            campus=payload["campus"],
            location=payload["location"],
            max_participants=payload["max_participants"],
            current_participants=0,
            registration_deadline=payload["registration_deadline"],
            cancel_deadline=payload["cancel_deadline"],
            description=payload["description"],
            status="draft",
        )
        session.add(activity)
        session.flush()
        return success({"activity_id": activity.id, "status": activity.status}, message="活动创建成功")


@bp.post("/organizer/activities/<int:activity_id>/submit")
@bp.put("/activities/<int:activity_id>/submit")
@role_required("organizer")
def submit_activity(activity_id):
    with db_session() as session:
        activity = load_activity_for_organizer(session, activity_id)
        if activity.status in ("open", "ongoing", "edit_pending"):
            activity.status = "edit_pending"
        else:
            activity.status = "pending"
        activity.reject_reason = None
        return success({"activity_id": activity.id, "status": activity.status}, message="已提交审核")


@bp.get("/activities")
def list_activities():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)

    with db_session() as session:
        query = session.query(Activity)

        if keyword := str(request.args.get("keyword") or request.args.get("name") or "").strip():
            query = query.filter(Activity.name.contains(keyword))
        if category_id := request.args.get("category_id"):
            try:
                query = query.filter(Activity.category_id == int(category_id))
            except ValueError as exc:
                raise ApiError("分类ID无效") from exc
        if campus := str(request.args.get("campus") or "").strip():
            query = query.filter(Activity.campus == campus)
        statuses = list_statuses(request.args.get("status"))
        if statuses:
            query = query.filter(Activity.status.in_(statuses))
        else:
            query = query.filter(Activity.status.in_(("open", "ongoing", "edit_pending")))
        if organizer_id := request.args.get("organizer_id"):
            try:
                query = query.filter(Activity.organizer_id == int(organizer_id))
            except ValueError as exc:
                raise ApiError("组织者ID无效") from exc
        if start_date := request.args.get("start_date"):
            start_time = parse_datetime(start_date)
            if not start_time:
                raise ApiError("start_date无效")
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
        for row in rows:
            item = activity_list_item(row, include_status=False)
            item = enrich_activity_item(item, categories, row, include_status=False)
            items.append(item)

        return success({"total": total, "page": page, "page_size": page_size, "list": items})


@bp.get("/organizer/activities")
@bp.get("/activities/my")
@role_required("organizer")
def my_activities():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)

    with db_session() as session:
        query = session.query(Activity).filter(Activity.organizer_id == request.current_user_id)
        if keyword := str(request.args.get("keyword") or "").strip():
            query = query.filter(Activity.name.contains(keyword))
        if category_id := request.args.get("category_id"):
            try:
                query = query.filter(Activity.category_id == int(category_id))
            except ValueError as exc:
                raise ApiError("分类ID无效") from exc
        if campus := str(request.args.get("campus") or "").strip():
            query = query.filter(Activity.campus == campus)
        statuses = list_statuses(request.args.get("status"))
        if statuses:
            query = query.filter(Activity.status.in_(statuses))
        if start_date := request.args.get("start_date"):
            start_time = parse_datetime(start_date)
            if not start_time:
                raise ApiError("start_date无效")
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
        for row in rows:
            revision = get_revision(session, row.id) if row.status == "edit_pending" else None
            source = revision or row
            item = activity_list_item(source, include_status=True)
            item = enrich_activity_item(item, categories, row, include_status=True)
            items.append(item)

        return success({"total": total, "page": page, "page_size": page_size, "list": items})


@bp.get("/activities/<int:activity_id>")
def activity_detail(activity_id):
    role, user_id = optional_identity()

    with db_session() as session:
        activity = session.get(Activity, activity_id)
        if not activity or activity.status == "removed":
            raise ApiError("活动不存在", code=404, status_code=404)

        organizer = session.get(Organizer, activity.organizer_id)
        categories = category_map(session)
        revision = None
        if activity.status == "edit_pending" and role in ("admin", "organizer"):
            if role == "admin" or user_id == activity.organizer_id:
                revision = get_revision(session, activity_id)
        source = revision or activity
        registration = None
        checkin = None
        if role == "user" and user_id:
            registration = (
                session.query(Registration)
                .filter(Registration.activity_id == activity_id, Registration.user_id == user_id)
                .first()
            )
            checkin = (
                session.query(Checkin)
                .filter(Checkin.activity_id == activity_id, Checkin.user_id == user_id)
                .first()
            )

        return success(
            {
                "activity_id": activity.id,
                "organizer_id": activity.organizer_id,
                "organizer_name": organizer.org_name if organizer else None,
                "name": source.name,
                "category_id": source.category_id,
                "category_name": categories.get(source.category_id).name if categories.get(source.category_id) else None,
                "category_path": category_path(source.category_id, categories) if categories.get(source.category_id) else None,
                "start_time": dt(source.start_time),
                "end_time": dt(source.end_time),
                "campus": source.campus,
                "location": source.location,
                "max_participants": source.max_participants,
                "current_participants": activity.current_participants,
                "registration_deadline": dt(source.registration_deadline),
                "cancel_deadline": dt(source.cancel_deadline),
                "description": source.description,
                "status": activity.status,
                "is_registered": bool(registration and registration.status in ACTIVE_STATUSES),
                "registration_status": registration.status if registration else None,
                "check_status": bool(checkin),
            }
        )


@bp.put("/organizer/activities/<int:activity_id>")
@bp.put("/activities/<int:activity_id>")
@role_required("organizer")
def update_activity(activity_id):
    data = request.get_json(silent=True) or {}
    payload = normalized_payload(data)

    with db_session() as session:
        activity = load_activity_for_organizer(session, activity_id)
        if not session.get(Category, payload["category_id"]):
            raise ApiError("活动分类不存在", code=404, status_code=404)

        if activity.status in EDITABLE_DIRECT_STATUSES:
            apply_activity_fields(activity, payload)
        else:
            revision = get_revision(session, activity.id)
            if not revision:
                revision = ActivityRevision(
                    activity_id=activity.id,
                    organizer_id=activity.organizer_id,
                    category_id=payload["category_id"],
                    name=payload["name"],
                    start_time=payload["start_time"],
                    end_time=payload["end_time"],
                    campus=payload["campus"],
                    location=payload["location"],
                    max_participants=payload["max_participants"],
                    registration_deadline=payload["registration_deadline"],
                    cancel_deadline=payload["cancel_deadline"],
                    description=payload["description"],
                )
                session.add(revision)
            else:
                apply_revision_fields(revision, payload)
            activity.status = "edit_pending"
        activity.reject_reason = None
        session.flush()
        return success({"activity_id": activity.id, "status": activity.status}, message="活动更新成功")


@bp.delete("/organizer/activities/<int:activity_id>")
@bp.delete("/activities/<int:activity_id>")
@role_required("organizer")
def delete_activity(activity_id):
    with db_session() as session:
        activity = load_activity_for_organizer(session, activity_id)
        activity.status = "removed"
        revision = get_revision(session, activity_id)
        if revision:
            session.delete(revision)
        session.flush()

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
                "Activity Cancelled",
                f"The activity {activity.name} was cancelled.",
                "activity_audit_result",
                activity.id,
            )
        return success(None, message="活动已删除，已通知所有报名用户")
