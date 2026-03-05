from __future__ import annotations

import os
import time
from typing import Dict, Tuple

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_client: redis.Redis | None = None
_use_memory_fallback = os.getenv("TESTING", "").lower() == "true"

# In-memory fallback para tests (almacena token_jti -> timestamp de expiración)
_memory_blacklist: Dict[str, float] = {}


def _get_redis() -> redis.Redis | None:
    """Obtiene cliente Redis singleton. Retorna None si estamos en modo test."""
    global _redis_client, _use_memory_fallback
    if _use_memory_fallback:
        return None
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            _redis_client.ping()  # Verificar conexión
        except redis.ConnectionError:
            _use_memory_fallback = True
            return None
    return _redis_client


def add_to_blacklist(token_jti: str, ttl_seconds: int) -> None:
    """Agrega token a blacklist con TTL."""
    client = _get_redis()
    if client:
        key = f"blacklist:{token_jti}"
        client.setex(key, ttl_seconds, "1")
    else:
        # Fallback a memoria
        _memory_blacklist[token_jti] = time.time() + ttl_seconds


def is_blacklisted(token_jti: str) -> bool:
    """Verifica si token está en blacklist."""
    client = _get_redis()
    if client:
        key = f"blacklist:{token_jti}"
        return client.exists(key) > 0
    else:
        # Fallback a memoria
        expiry = _memory_blacklist.get(token_jti)
        if expiry is None:
            return False
        if time.time() > expiry:
            del _memory_blacklist[token_jti]
            return False
        return True


def _reset_for_testing() -> None:
    """Reset del estado para tests. Solo usar en tests."""
    global _use_memory_fallback, _memory_blacklist, _redis_client
    _use_memory_fallback = True
    _memory_blacklist = {}
    _redis_client = None
