from flask import Blueprint

from app.api.v1.auth import bp as auth_bp
from app.api.v1.admin_activities import bp as admin_activities_bp
from app.api.v1.activities import bp as activities_bp
from app.api.v1.categories import bp as categories_bp
from app.api.v1.checkin import bp as checkin_bp
from app.api.v1.health import bp as health_bp
from app.api.v1.notifications import bp as notifications_bp
from app.api.v1.registrations import bp as registrations_bp
from app.api.v1.user import bp as user_bp

api_v1 = Blueprint("api_v1", __name__)
api_v1.register_blueprint(health_bp)
api_v1.register_blueprint(auth_bp)
api_v1.register_blueprint(admin_activities_bp)
api_v1.register_blueprint(user_bp)
api_v1.register_blueprint(activities_bp)
api_v1.register_blueprint(categories_bp)
api_v1.register_blueprint(registrations_bp)
api_v1.register_blueprint(checkin_bp)
api_v1.register_blueprint(notifications_bp)
