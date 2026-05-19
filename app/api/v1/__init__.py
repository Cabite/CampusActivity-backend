from flask import Blueprint

from app.api.v1.categories import bp as categories_bp
from app.api.v1.health import bp as health_bp

api_v1 = Blueprint("api_v1", __name__)
api_v1.register_blueprint(health_bp)
api_v1.register_blueprint(categories_bp)
