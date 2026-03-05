from __future__ import annotations

from flask import Blueprint, request, jsonify

from ..extensions import db
from ..models import User
from ..services.auth_service import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    AuthError,
    ACCESS_TOKEN_EXPIRES_SECONDS,
)
from ..services.token_blacklist import add_to_blacklist
from ..middleware import require_auth, get_current_user
from ..time_utils import now_cordoba_naive
from ..extensions import limiter

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/auth/login")
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "username y password son requeridos"}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "Credenciales inválidas"}), 401

    if not user.activo:
        return jsonify({"error": "Usuario desactivado"}), 401

    if not verify_password(password, user.password_hash):
        return jsonify({"error": "Credenciales inválidas"}), 401

    # Actualizar last_login_at
    user.last_login_at = now_cordoba_naive()
    db.session.commit()

    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        rol=user.rol,
    )
    refresh_token = create_refresh_token(user_id=user.id)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict(),
    }), 200


@auth_bp.post("/auth/logout")
@require_auth
def logout():
    token = request.headers.get("Authorization", "")[7:]
    try:
        payload = decode_token(token)
        token_id = str(payload.get("iat", ""))
        add_to_blacklist(token_id, ttl_seconds=ACCESS_TOKEN_EXPIRES_SECONDS)
    except AuthError:
        pass  # Token ya inválido, ignorar

    return jsonify({"message": "Sesión cerrada"}), 200


@auth_bp.get("/auth/me")
@require_auth
def me():
    current = get_current_user()
    user = db.session.get(User, current["id"])
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify(user.to_dict()), 200


@auth_bp.post("/auth/refresh")
def refresh():
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token", "")

    if not refresh_token:
        return jsonify({"error": "refresh_token es requerido"}), 400

    try:
        payload = decode_token(refresh_token)
    except AuthError as e:
        return jsonify({"error": str(e)}), 401

    if payload.get("type") != "refresh":
        return jsonify({"error": "Tipo de token inválido"}), 400

    user = db.session.get(User, payload["user_id"])
    if not user or not user.activo:
        return jsonify({"error": "Usuario no válido"}), 401

    new_access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        rol=user.rol,
    )

    return jsonify({"access_token": new_access_token}), 200
