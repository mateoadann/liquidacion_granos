from flask import Blueprint, current_app, jsonify
import redis

from ..extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health_check():
    db_ok = True
    redis_ok = True

    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        db_ok = False

    try:
        client = redis.from_url(current_app.config["REDIS_URL"])
        client.ping()
    except Exception:
        redis_ok = False

    status_code = 200 if db_ok and redis_ok else 503

    return (
        jsonify(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "database": "ok" if db_ok else "error",
                "redis": "ok" if redis_ok else "error",
            }
        ),
        status_code,
    )
