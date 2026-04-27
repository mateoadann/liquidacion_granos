from __future__ import annotations

import hmac
from functools import wraps
from typing import Callable

from flask import current_app, g, request, jsonify

from ..services.auth_service import decode_token, AuthError
from ..services.token_blacklist import is_blacklisted


def get_current_user() -> dict | None:
    """Retorna usuario actual del contexto de request."""
    return getattr(g, "current_user", None)


def _extract_token_from_header() -> str | None:
    """Extrae token del header Authorization: Bearer <token>."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]


def require_auth(f: Callable) -> Callable:
    """Decorator que requiere autenticacion JWT valida."""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token_from_header()
        if not token:
            return jsonify({"error": "Token no proporcionado"}), 401

        try:
            payload = decode_token(token)
        except AuthError as e:
            return jsonify({"error": str(e)}), 401

        if payload.get("type") != "access":
            return jsonify({"error": "Tipo de token invalido"}), 401

        # Verificar blacklist usando iat como identificador
        token_id = str(payload.get("iat", ""))
        if is_blacklisted(token_id):
            return jsonify({"error": "Token revocado"}), 401

        g.current_user = {
            "id": payload["user_id"],
            "username": payload["username"],
            "rol": payload["rol"],
        }

        return f(*args, **kwargs)

    return decorated


def require_api_key(f: Callable) -> Callable:
    """Decorator que requiere X-API-Key valida (timing-safe)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "")
        expected = current_app.config.get("LIQUIDADOR_API_KEY", "")
        if not expected or not hmac.compare_digest(api_key, expected):
            return jsonify({"error": "api_key_invalida", "mensaje": "X-API-Key faltante o inválida."}), 401
        return f(*args, **kwargs)

    return decorated


def require_admin(f: Callable) -> Callable:
    """Decorator que requiere rol admin. Debe usarse despues de require_auth."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "No autenticado"}), 401

        if user.get("rol") != "admin":
            return jsonify({"error": "Acceso denegado: se requiere rol admin"}), 403

        return f(*args, **kwargs)

    return decorated
