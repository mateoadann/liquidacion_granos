from __future__ import annotations

from flask import Blueprint, request

from ..extensions import db
from ..models import User
from ..middleware import require_auth, require_admin

users_bp = Blueprint("users", __name__)


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nombre": user.nombre,
        "rol": user.rol,
        "activo": user.activo,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _count_active_admins() -> int:
    return User.query.filter_by(rol="admin", activo=True).count()


def _is_last_active_admin(user: User) -> bool:
    if user.rol != "admin" or not user.activo:
        return False
    return _count_active_admins() == 1


@users_bp.get("/users")
@require_auth
@require_admin
def list_users():
    users = User.query.order_by(User.nombre).all()
    return {"users": [_serialize_user(u) for u in users]}


@users_bp.get("/users/<int:user_id>")
@require_auth
@require_admin
def get_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404
    return _serialize_user(user)


@users_bp.post("/users")
@require_auth
@require_admin
def create_user():
    data = request.get_json(silent=True) or {}

    username = data.get("username", "").strip()
    nombre = data.get("nombre", "").strip()
    password = data.get("password", "")
    rol = data.get("rol", "usuario")

    if not username or not nombre or not password:
        return {"error": "username, nombre y password son requeridos"}, 400

    if len(password) < 8:
        return {"error": "La contraseña debe tener al menos 8 caracteres"}, 400

    if User.query.filter_by(username=username).first():
        return {"error": "El username ya existe"}, 409

    user = User()
    user.username = username
    user.nombre = nombre
    user.rol = rol if rol in ("admin", "usuario") else "usuario"
    user.set_password(password)
    user.activo = True

    db.session.add(user)
    db.session.commit()

    return _serialize_user(user), 201


@users_bp.patch("/users/<int:user_id>")
@require_auth
@require_admin
def update_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404

    data = request.get_json(silent=True) or {}

    # Validar restricción de último admin
    is_last_admin = _is_last_active_admin(user)

    if is_last_admin:
        if data.get("activo") is False:
            return {"error": "No se puede desactivar al último admin activo"}, 400
        if data.get("rol") == "usuario":
            return {"error": "No se puede cambiar el rol del último admin activo"}, 400

    if "nombre" in data:
        user.nombre = data["nombre"].strip()

    if "rol" in data and data["rol"] in ("admin", "usuario"):
        user.rol = data["rol"]

    if "activo" in data:
        user.activo = bool(data["activo"])

    db.session.commit()

    return _serialize_user(user)


@users_bp.delete("/users/<int:user_id>")
@require_auth
@require_admin
def delete_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404

    if _is_last_active_admin(user):
        return {"error": "No se puede eliminar al último admin activo"}, 400

    db.session.delete(user)
    db.session.commit()

    return "", 204


@users_bp.post("/users/<int:user_id>/reset-password")
@require_auth
@require_admin
def reset_password(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404

    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password", "")

    if len(new_password) < 8:
        return {"error": "La contraseña debe tener al menos 8 caracteres"}, 400

    user.set_password(new_password)
    db.session.commit()

    return {"message": "Contraseña actualizada"}
