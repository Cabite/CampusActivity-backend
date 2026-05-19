from flask import Blueprint

from app.common.database import db_session
from app.common.response import success
from app.services.category_service import list_category_tree

bp = Blueprint("categories", __name__, url_prefix="/categories")


@bp.get("")
def get_categories():
    """API example: GET /api/categories."""
    with db_session() as session:
        return success(list_category_tree(session))
