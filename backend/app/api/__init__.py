from flask import Flask

from .clients import clients_bp
from .discovery import discovery_bp
from .health import health_bp
from .jobs import jobs_bp
from .operations import operations_bp
from .playwright import playwright_bp
from .taxpayers import taxpayers_bp
from .wslpg_mvp import wslpg_mvp_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(operations_bp, url_prefix="/api")
    app.register_blueprint(playwright_bp, url_prefix="/api")
    app.register_blueprint(clients_bp, url_prefix="/api")
    app.register_blueprint(taxpayers_bp, url_prefix="/api")
    app.register_blueprint(jobs_bp, url_prefix="/api")
    app.register_blueprint(discovery_bp, url_prefix="/api")
    app.register_blueprint(wslpg_mvp_bp, url_prefix="/api")
