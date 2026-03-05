from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db, migrate
from .api import register_blueprints
from .logging_setup import configure_logging
from .cli import register_cli


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    configure_logging(app.config.get("LOG_LEVEL"))

    CORS(app, origins=app.config.get("CORS_ORIGINS", "*"))
    db.init_app(app)
    migrate.init_app(app, db)

    # Registrar modelos para SQLAlchemy/Alembic autogenerate
    from . import models  # noqa: F401

    register_blueprints(app)
    register_cli(app)
    return app
