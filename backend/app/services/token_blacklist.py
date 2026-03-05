from __future__ import annotations

import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """Obtiene cliente Redis singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def add_to_blacklist(token_jti: str, ttl_seconds: int) -> None:
    """Agrega token a blacklist con TTL."""
    client = _get_redis()
    key = f"blacklist:{token_jti}"
    client.setex(key, ttl_seconds, "1")


def is_blacklisted(token_jti: str) -> bool:
    """Verifica si token está en blacklist."""
    client = _get_redis()
    key = f"blacklist:{token_jti}"
    return client.exists(key) > 0
