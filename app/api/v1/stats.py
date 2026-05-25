from flask import Blueprint, request

from app.common.database import db_session
from app.common.response import success
from models import Checkin, Registration, User

bp = Blueprint("stats", __name__, url_prefix="")


@bp.get("/leaderboard")
def leaderboard():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    with db_session() as session:
        users = session.query(User).filter(User.status == "active").all()
        rows = []
        for user in users:
            registration_count = session.query(Registration).filter(Registration.user_id == user.id).count()
            effective_count = session.query(Checkin).filter(Checkin.user_id == user.id).count()
            rows.append((user, registration_count, effective_count))
        rows.sort(key=lambda item: item[2], reverse=True)
        total = len(rows)
        page_rows = rows[(page - 1) * page_size : page * page_size]
        return success(
            {
                "total": total,
                "list": [
                    {
                        "rank": (page - 1) * page_size + index + 1,
                        "user_id": user.id,
                        "student_id": user.student_id,
                        "college": user.college,
                        "grade": user.grade,
                        "registration_count": registration_count,
                        "effective_participation_count": effective_count,
                    }
                    for index, (user, registration_count, effective_count) in enumerate(page_rows)
                ],
            }
        )
