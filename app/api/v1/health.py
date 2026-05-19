from flask import Blueprint

from app.common.response import success

bp = Blueprint("health", __name__)


@bp.get("/health")
def health_check():
    return success({"service": "campus-activity-api", "status": "ok"})
