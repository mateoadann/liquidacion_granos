from __future__ import annotations

from flask import current_app
from redis import Redis
from rq import Queue


def get_redis_connection() -> Redis:
    redis_url = current_app.config["REDIS_URL"]
    return Redis.from_url(redis_url)


def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis_connection())
