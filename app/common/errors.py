from werkzeug.exceptions import HTTPException

from app.common.response import fail


class ApiError(Exception):
    def __init__(self, message, code=400, status_code=400, data=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.data = data


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        return fail(error.message, code=error.code, data=error.data), error.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return fail(error.description, code=error.code), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception(error)
        return fail("服务器内部错误", code=500), 500
