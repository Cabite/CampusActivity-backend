from flask import Flask

from config import get_config
from app.api.v1 import api_v1
from app.common.errors import register_error_handlers


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    app.register_blueprint(api_v1)
    app.register_blueprint(api_v1, url_prefix="/api", name="api_v1_legacy")
    register_error_handlers(app)
    register_cors_headers(app)

    return app


def register_cors_headers(app):
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response
