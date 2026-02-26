from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db, migrate
from .api import register_blueprints


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    CORS(app, origins=app.config.get("CORS_ORIGINS", "*"))
    db.init_app(app)
    migrate.init_app(app, db)

    # Registrar modelos para SQLAlchemy/Alembic autogenerate
    from . import models  # noqa: F401

    register_blueprints(app)
    return app
