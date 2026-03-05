# Auth + Login Implementation Plan (Fase 1)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implementar sistema de autenticación completo con JWT, modelo de usuarios, y página de login en el frontend.

**Architecture:** Backend Flask con JWT (PyJWT), bcrypt para passwords, Redis para blacklist de tokens y rate limiting. Frontend React con React Router v6, Zustand para estado de auth, y componentes UI base con Tailwind.

**Tech Stack:** Flask, PyJWT, bcrypt, Flask-Limiter, Redis | React 18, React Router v6, Zustand, Tailwind CSS, Inter font

---

## Task 1: Agregar dependencias backend

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: Agregar dependencias de auth**

Agregar al final de `backend/requirements.txt`:

```
PyJWT>=2.8,<3
bcrypt>=4.1,<5
Flask-Limiter>=3.5,<4
```

**Step 2: Instalar dependencias**

Run: `cd backend && pip install -r requirements.txt`
Expected: Instalación exitosa sin errores

**Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add auth dependencies (PyJWT, bcrypt, Flask-Limiter)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Crear modelo User

**Files:**
- Create: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: Crear archivo del modelo**

Crear `backend/app/models/user.py`:

```python
from __future__ import annotations

from ..extensions import db
from ..time_utils import now_cordoba_naive


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="usuario")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=now_cordoba_naive,
        onupdate=now_cordoba_naive,
    )
    last_login_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "nombre": self.nombre,
            "rol": self.rol,
            "activo": self.activo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }
```

**Step 2: Exportar modelo en __init__.py**

Modificar `backend/app/models/__init__.py`:

```python
from .taxpayer import Taxpayer
from .extraction_job import ExtractionJob
from .lpg_document import LpgDocument
from .audit_event import AuditEvent
from .user import User

__all__ = ["Taxpayer", "ExtractionJob", "LpgDocument", "AuditEvent", "User"]
```

**Step 3: Commit**

```bash
git add backend/app/models/user.py backend/app/models/__init__.py
git commit -m "feat(auth): add User model

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Crear migración para tabla users

**Step 1: Generar migración**

Run: `cd backend && flask db migrate -m "add users table"`
Expected: Archivo de migración creado en `backend/migrations/versions/`

**Step 2: Verificar migración generada**

Abrir el archivo generado y verificar que contiene:
- Creación de tabla `users`
- Columnas: id, username, password_hash, nombre, rol, activo, created_at, updated_at, last_login_at
- Índice único en username

**Step 3: Aplicar migración**

Run: `cd backend && flask db upgrade`
Expected: Migración aplicada exitosamente

**Step 4: Commit**

```bash
git add backend/migrations/
git commit -m "feat(auth): add users table migration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Crear servicio de autenticación

**Files:**
- Create: `backend/app/services/auth_service.py`
- Test: `backend/tests/unit/test_auth_service.py`

**Step 1: Escribir tests del servicio**

Crear `backend/tests/unit/test_auth_service.py`:

```python
from __future__ import annotations

import pytest

from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    AuthError,
)


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        password = "mi_password_seguro"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self):
        password = "mi_password_seguro"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        password = "mi_password_seguro"
        hashed = hash_password(password)

        assert verify_password("password_incorrecto", hashed) is False


class TestJwtTokens:
    def test_create_access_token_returns_string(self):
        token = create_access_token(user_id=1, username="admin", rol="admin")

        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token_returns_payload(self):
        token = create_access_token(user_id=1, username="admin", rol="admin")
        payload = decode_token(token)

        assert payload["user_id"] == 1
        assert payload["username"] == "admin"
        assert payload["rol"] == "admin"
        assert payload["type"] == "access"

    def test_create_refresh_token_returns_string(self):
        token = create_refresh_token(user_id=1)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_refresh_token_returns_payload(self):
        token = create_refresh_token(user_id=1)
        payload = decode_token(token)

        assert payload["user_id"] == 1
        assert payload["type"] == "refresh"

    def test_decode_invalid_token_raises_error(self):
        with pytest.raises(AuthError) as exc_info:
            decode_token("token.invalido.aqui")

        assert "Token inválido" in str(exc_info.value)

    def test_decode_expired_token_raises_error(self, monkeypatch):
        import time
        from app.services import auth_service

        # Crear token con expiración de 1 segundo
        monkeypatch.setattr(auth_service, "ACCESS_TOKEN_EXPIRES_SECONDS", 1)
        token = create_access_token(user_id=1, username="admin", rol="admin")

        time.sleep(2)

        with pytest.raises(AuthError) as exc_info:
            decode_token(token)

        assert "Token expirado" in str(exc_info.value)
```

**Step 2: Ejecutar tests y verificar que fallan**

Run: `cd backend && pytest tests/unit/test_auth_service.py -v`
Expected: FAIL - módulo no existe

**Step 3: Implementar servicio de auth**

Crear `backend/app/services/auth_service.py`:

```python
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ACCESS_TOKEN_EXPIRES_SECONDS = 15 * 60  # 15 minutos
REFRESH_TOKEN_EXPIRES_SECONDS = 7 * 24 * 60 * 60  # 7 días


class AuthError(Exception):
    """Error de autenticación."""

    pass


def hash_password(password: str) -> str:
    """Hash de password usando bcrypt con cost factor 12."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verifica password contra hash bcrypt."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, user_id: int, username: str, rol: str) -> str:
    """Crea JWT de acceso con expiración corta."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "username": username,
        "rol": rol,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=ACCESS_TOKEN_EXPIRES_SECONDS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def create_refresh_token(*, user_id: int) -> str:
    """Crea JWT de refresh con expiración larga."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(seconds=REFRESH_TOKEN_EXPIRES_SECONDS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decodifica y valida JWT. Lanza AuthError si es inválido o expirado."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expirado")
    except jwt.InvalidTokenError:
        raise AuthError("Token inválido")
```

**Step 4: Ejecutar tests y verificar que pasan**

Run: `cd backend && pytest tests/unit/test_auth_service.py -v`
Expected: PASS - todos los tests pasan

**Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/unit/test_auth_service.py
git commit -m "feat(auth): add auth service with JWT and bcrypt

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Crear servicio de blacklist de tokens (Redis)

**Files:**
- Create: `backend/app/services/token_blacklist.py`
- Test: `backend/tests/unit/test_token_blacklist.py`

**Step 1: Escribir tests del blacklist**

Crear `backend/tests/unit/test_token_blacklist.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestTokenBlacklist:
    @patch("app.services.token_blacklist._get_redis")
    def test_add_to_blacklist(self, mock_get_redis):
        from app.services.token_blacklist import add_to_blacklist

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        add_to_blacklist("test-token-jti", ttl_seconds=900)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert "blacklist:test-token-jti" in call_args[0][0]
        assert call_args[0][1] == 900

    @patch("app.services.token_blacklist._get_redis")
    def test_is_blacklisted_returns_true_when_exists(self, mock_get_redis):
        from app.services.token_blacklist import is_blacklisted

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        mock_get_redis.return_value = mock_redis

        result = is_blacklisted("test-token-jti")

        assert result is True

    @patch("app.services.token_blacklist._get_redis")
    def test_is_blacklisted_returns_false_when_not_exists(self, mock_get_redis):
        from app.services.token_blacklist import is_blacklisted

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0
        mock_get_redis.return_value = mock_redis

        result = is_blacklisted("test-token-jti")

        assert result is False
```

**Step 2: Ejecutar tests y verificar que fallan**

Run: `cd backend && pytest tests/unit/test_token_blacklist.py -v`
Expected: FAIL - módulo no existe

**Step 3: Implementar servicio de blacklist**

Crear `backend/app/services/token_blacklist.py`:

```python
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
```

**Step 4: Ejecutar tests y verificar que pasan**

Run: `cd backend && pytest tests/unit/test_token_blacklist.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/token_blacklist.py backend/tests/unit/test_token_blacklist.py
git commit -m "feat(auth): add token blacklist service with Redis

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Crear middleware de autenticación

**Files:**
- Create: `backend/app/middleware/auth_middleware.py`
- Create: `backend/app/middleware/__init__.py`

**Step 1: Crear directorio middleware**

Crear `backend/app/middleware/__init__.py`:

```python
from .auth_middleware import require_auth, require_admin, get_current_user

__all__ = ["require_auth", "require_admin", "get_current_user"]
```

**Step 2: Implementar middleware**

Crear `backend/app/middleware/auth_middleware.py`:

```python
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import g, request, jsonify

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
    """Decorator que requiere autenticación JWT válida."""

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
            return jsonify({"error": "Tipo de token inválido"}), 401

        # Verificar blacklist usando jti (JWT ID) o iat como identificador
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


def require_admin(f: Callable) -> Callable:
    """Decorator que requiere rol admin. Debe usarse después de require_auth."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "No autenticado"}), 401

        if user.get("rol") != "admin":
            return jsonify({"error": "Acceso denegado: se requiere rol admin"}), 403

        return f(*args, **kwargs)

    return decorated
```

**Step 3: Commit**

```bash
git add backend/app/middleware/
git commit -m "feat(auth): add auth middleware with JWT validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Crear endpoints de auth

**Files:**
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/integration/test_auth_api.py`

**Step 1: Escribir tests de integración**

Crear `backend/tests/integration/test_auth_api.py`:

```python
from __future__ import annotations

from app.extensions import db
from app.models import User
from app.services.auth_service import hash_password


def _create_user(*, username: str, password: str, nombre: str, rol: str = "usuario") -> User:
    user = User()
    user.username = username
    user.password_hash = hash_password(password)
    user.nombre = nombre
    user.rol = rol
    user.activo = True
    db.session.add(user)
    db.session.commit()
    return user


class TestLoginEndpoint:
    def test_login_success_returns_tokens(self, client):
        _create_user(username="testuser", password="password123", nombre="Test User")

        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password123"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["username"] == "testuser"

    def test_login_wrong_password_returns_401(self, client):
        _create_user(username="testuser", password="password123", nombre="Test User")

        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "wrongpassword"},
        )

        assert response.status_code == 401
        assert "error" in response.get_json()

    def test_login_nonexistent_user_returns_401(self, client):
        response = client.post(
            "/api/auth/login",
            json={"username": "noexiste", "password": "password123"},
        )

        assert response.status_code == 401

    def test_login_inactive_user_returns_401(self, client):
        user = _create_user(username="inactive", password="password123", nombre="Inactive")
        user.activo = False
        db.session.commit()

        response = client.post(
            "/api/auth/login",
            json={"username": "inactive", "password": "password123"},
        )

        assert response.status_code == 401

    def test_login_missing_fields_returns_400(self, client):
        response = client.post("/api/auth/login", json={})

        assert response.status_code == 400


class TestMeEndpoint:
    def test_me_with_valid_token_returns_user(self, client):
        _create_user(username="testuser", password="password123", nombre="Test User", rol="admin")

        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password123"},
        )
        token = login_response.get_json()["access_token"]

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["username"] == "testuser"
        assert data["rol"] == "admin"

    def test_me_without_token_returns_401(self, client):
        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401


class TestLogoutEndpoint:
    def test_logout_invalidates_token(self, client):
        _create_user(username="testuser", password="password123", nombre="Test User")

        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password123"},
        )
        token = login_response.get_json()["access_token"]

        # Logout
        logout_response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_response.status_code == 200

        # Token should now be invalid
        me_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_response.status_code == 401


class TestRefreshEndpoint:
    def test_refresh_returns_new_access_token(self, client):
        _create_user(username="testuser", password="password123", nombre="Test User")

        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password123"},
        )
        refresh_token = login_response.get_json()["refresh_token"]

        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        assert "access_token" in response.get_json()

    def test_refresh_with_access_token_returns_400(self, client):
        _create_user(username="testuser", password="password123", nombre="Test User")

        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password123"},
        )
        access_token = login_response.get_json()["access_token"]

        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": access_token},
        )

        assert response.status_code == 400
```

**Step 2: Ejecutar tests y verificar que fallan**

Run: `cd backend && pytest tests/integration/test_auth_api.py -v`
Expected: FAIL - blueprint no existe

**Step 3: Implementar endpoints de auth**

Crear `backend/app/api/auth.py`:

```python
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

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/auth/login")
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
    user = User.query.get(current["id"])
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

    user = User.query.get(payload["user_id"])
    if not user or not user.activo:
        return jsonify({"error": "Usuario no válido"}), 401

    new_access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        rol=user.rol,
    )

    return jsonify({"access_token": new_access_token}), 200
```

**Step 4: Registrar blueprint**

Modificar `backend/app/api/__init__.py`:

```python
from flask import Flask

from .auth import auth_bp
from .clients import clients_bp
from .discovery import discovery_bp
from .health import health_bp
from .jobs import jobs_bp
from .operations import operations_bp
from .playwright import playwright_bp
from .taxpayers import taxpayers_bp
from .wslpg_mvp import wslpg_mvp_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(operations_bp, url_prefix="/api")
    app.register_blueprint(playwright_bp, url_prefix="/api")
    app.register_blueprint(clients_bp, url_prefix="/api")
    app.register_blueprint(taxpayers_bp, url_prefix="/api")
    app.register_blueprint(jobs_bp, url_prefix="/api")
    app.register_blueprint(discovery_bp, url_prefix="/api")
    app.register_blueprint(wslpg_mvp_bp, url_prefix="/api")
```

**Step 5: Ejecutar tests y verificar que pasan**

Run: `cd backend && pytest tests/integration/test_auth_api.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/api/auth.py backend/app/api/__init__.py backend/tests/integration/test_auth_api.py
git commit -m "feat(auth): add auth API endpoints (login, logout, me, refresh)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Agregar rate limiting al login

**Files:**
- Modify: `backend/app/__init__.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/config.py`

**Step 1: Agregar config de rate limit**

Agregar a `backend/app/config.py`:

```python
import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    CLIENT_SECRET_KEY = os.getenv("CLIENT_SECRET_KEY", SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://liquidacion:liquidacion@localhost:5432/liquidacion_granos",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CLIENT_CERTIFICATES_BASE_PATH = os.getenv(
        "CLIENT_CERTIFICATES_BASE_PATH", "/app/certificados_clientes"
    )
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Rate limiting
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_DEFAULT = "200 per minute"
    RATELIMIT_HEADERS_ENABLED = True
```

**Step 2: Inicializar Flask-Limiter en app**

Modificar `backend/app/__init__.py`:

```python
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .config import Config
from .extensions import db, migrate
from .api import register_blueprints
from .logging_setup import configure_logging

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
)


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    configure_logging(app.config.get("LOG_LEVEL"))

    CORS(app, origins=app.config.get("CORS_ORIGINS", "*"))
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # Registrar modelos para SQLAlchemy/Alembic autogenerate
    from . import models  # noqa: F401

    register_blueprints(app)
    return app
```

**Step 3: Aplicar rate limit al endpoint de login**

Modificar `backend/app/api/auth.py`, agregar import y decorator:

```python
from __future__ import annotations

from flask import Blueprint, request, jsonify

from .. import limiter
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

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/auth/login")
@limiter.limit("5 per minute")
def login():
    # ... resto del código igual
```

**Step 4: Commit**

```bash
git add backend/app/__init__.py backend/app/api/auth.py backend/app/config.py
git commit -m "feat(auth): add rate limiting to login endpoint (5/min)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Crear comando CLI para crear admin

**Files:**
- Create: `backend/app/cli.py`
- Modify: `backend/app/__init__.py`

**Step 1: Crear módulo CLI**

Crear `backend/app/cli.py`:

```python
from __future__ import annotations

import click
from flask import Flask

from .extensions import db
from .models import User
from .services.auth_service import hash_password


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--username", required=True, help="Username del admin")
    @click.option("--password", required=True, help="Password del admin (min 8 chars)")
    @click.option("--nombre", required=True, help="Nombre completo del admin")
    def create_admin(username: str, password: str, nombre: str):
        """Crea el usuario administrador inicial."""
        if len(password) < 8:
            click.echo("Error: El password debe tener al menos 8 caracteres", err=True)
            raise SystemExit(1)

        existing_admin = User.query.filter_by(rol="admin").first()
        if existing_admin:
            click.echo(f"Error: Ya existe un admin: {existing_admin.username}", err=True)
            raise SystemExit(1)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            click.echo(f"Error: Ya existe un usuario con username: {username}", err=True)
            raise SystemExit(1)

        user = User()
        user.username = username
        user.password_hash = hash_password(password)
        user.nombre = nombre
        user.rol = "admin"
        user.activo = True

        db.session.add(user)
        db.session.commit()

        click.echo(f"Admin creado exitosamente: {username}")
```

**Step 2: Registrar CLI en app**

Modificar `backend/app/__init__.py`, agregar al final de create_app:

```python
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .config import Config
from .extensions import db, migrate
from .api import register_blueprints
from .logging_setup import configure_logging
from .cli import register_cli

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
)


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    configure_logging(app.config.get("LOG_LEVEL"))

    CORS(app, origins=app.config.get("CORS_ORIGINS", "*"))
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # Registrar modelos para SQLAlchemy/Alembic autogenerate
    from . import models  # noqa: F401

    register_blueprints(app)
    register_cli(app)
    return app
```

**Step 3: Verificar comando**

Run: `cd backend && flask create-admin --help`
Expected: Muestra ayuda del comando

**Step 4: Commit**

```bash
git add backend/app/cli.py backend/app/__init__.py
git commit -m "feat(auth): add CLI command to create initial admin user

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Agregar fuente Inter al frontend

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/tailwind.config.cjs`
- Modify: `frontend/src/styles.css`

**Step 1: Agregar link a Inter en index.html**

Modificar `frontend/index.html`:

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <title>Liquidación de Granos</title>
  </head>
  <body class="bg-slate-50 font-sans">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 2: Configurar Inter en Tailwind**

Modificar `frontend/tailwind.config.cjs`:

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
```

**Step 3: Commit**

```bash
git add frontend/index.html frontend/tailwind.config.cjs
git commit -m "feat(ui): add Inter font from Google Fonts

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Agregar React Router al frontend

**Files:**
- Modify: `frontend/package.json`

**Step 1: Instalar React Router**

Run: `cd frontend && npm install react-router-dom`
Expected: Instalación exitosa

**Step 2: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add react-router-dom dependency

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Crear componentes UI base (Button, Input, Alert, Spinner)

**Files:**
- Create: `frontend/src/components/ui/Button.tsx`
- Create: `frontend/src/components/ui/Input.tsx`
- Create: `frontend/src/components/ui/Alert.tsx`
- Create: `frontend/src/components/ui/Spinner.tsx`
- Create: `frontend/src/components/ui/index.ts`

**Step 1: Crear directorio components/ui**

Run: `mkdir -p frontend/src/components/ui frontend/src/components/layout`

**Step 2: Crear Button.tsx**

Crear `frontend/src/components/ui/Button.tsx`:

```tsx
import { type ButtonHTMLAttributes, forwardRef } from "react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-green-600 text-white hover:bg-green-700 focus:ring-green-500 disabled:bg-green-400",
  secondary:
    "border border-green-600 text-green-700 bg-transparent hover:bg-green-50 focus:ring-green-500",
  danger:
    "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 disabled:bg-red-400",
  ghost:
    "text-slate-700 bg-transparent hover:bg-slate-100 focus:ring-slate-500",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      isLoading = false,
      disabled,
      className = "",
      children,
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={`
          inline-flex items-center justify-center gap-2
          font-semibold rounded-md
          focus:outline-none focus:ring-2 focus:ring-offset-2
          transition-colors
          disabled:cursor-not-allowed disabled:opacity-60
          ${variantClasses[variant]}
          ${sizeClasses[size]}
          ${className}
        `}
        {...props}
      >
        {isLoading ? (
          <svg
            className="animate-spin h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : null}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
```

**Step 3: Crear Input.tsx**

Crear `frontend/src/components/ui/Input.tsx`:

```tsx
import { type InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, className = "", id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="w-full">
        {label ? (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-slate-700 mb-1"
          >
            {label}
          </label>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          className={`
            w-full px-3 py-2 rounded-md border text-sm
            focus:outline-none focus:ring-2 focus:ring-offset-0
            disabled:bg-slate-100 disabled:cursor-not-allowed
            ${
              error
                ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                : "border-slate-300 focus:ring-green-500 focus:border-green-500"
            }
            ${className}
          `}
          {...props}
        />
        {error ? (
          <p className="mt-1 text-xs text-red-600">{error}</p>
        ) : helperText ? (
          <p className="mt-1 text-xs text-slate-500">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Input.displayName = "Input";
```

**Step 4: Crear Alert.tsx**

Crear `frontend/src/components/ui/Alert.tsx`:

```tsx
import { type ReactNode } from "react";

type AlertVariant = "success" | "error" | "warning" | "info";

interface AlertProps {
  variant: AlertVariant;
  children: ReactNode;
  className?: string;
}

const variantClasses: Record<AlertVariant, string> = {
  success: "bg-emerald-50 border-emerald-200 text-emerald-700",
  error: "bg-red-50 border-red-200 text-red-700",
  warning: "bg-amber-50 border-amber-200 text-amber-700",
  info: "bg-blue-50 border-blue-200 text-blue-700",
};

export function Alert({ variant, children, className = "" }: AlertProps) {
  return (
    <div
      role="alert"
      className={`
        rounded-md border p-3 text-sm
        ${variantClasses[variant]}
        ${className}
      `}
    >
      {children}
    </div>
  );
}
```

**Step 5: Crear Spinner.tsx**

Crear `frontend/src/components/ui/Spinner.tsx`:

```tsx
interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
};

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <svg
      className={`animate-spin text-green-600 ${sizeClasses[size]} ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}
```

**Step 6: Crear index.ts para exports**

Crear `frontend/src/components/ui/index.ts`:

```tsx
export { Button } from "./Button";
export { Input } from "./Input";
export { Alert } from "./Alert";
export { Spinner } from "./Spinner";
```

**Step 7: Commit**

```bash
git add frontend/src/components/
git commit -m "feat(ui): add base UI components (Button, Input, Alert, Spinner)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Crear store de autenticación (Zustand)

**Files:**
- Create: `frontend/src/store/useAuthStore.ts`

**Step 1: Crear store de auth**

Crear `frontend/src/store/useAuthStore.ts`:

```tsx
import { create } from "zustand";

interface User {
  id: number;
  username: string;
  nombre: string;
  rol: "admin" | "usuario";
}

interface AuthState {
  accessToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  setAuth: (token: string, user: User) => void;
  clearAuth: () => void;
  updateToken: (token: string) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,

  setAuth: (token, user) =>
    set({
      accessToken: token,
      user,
      isAuthenticated: true,
    }),

  clearAuth: () =>
    set({
      accessToken: null,
      user: null,
      isAuthenticated: false,
    }),

  updateToken: (token) =>
    set({
      accessToken: token,
    }),
}));
```

**Step 2: Commit**

```bash
git add frontend/src/store/useAuthStore.ts
git commit -m "feat(auth): add Zustand auth store

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 14: Crear API client con interceptor de auth

**Files:**
- Create: `frontend/src/api/authApi.ts`
- Modify: `frontend/src/api/client.ts`

**Step 1: Crear authApi.ts**

Crear `frontend/src/api/authApi.ts`:

```tsx
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:5001/api";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: {
    id: number;
    username: string;
    nombre: string;
    rol: "admin" | "usuario";
  };
}

export interface RefreshResponse {
  access_token: string;
}

export async function login(data: LoginRequest): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  const json = await res.json();
  if (!res.ok) {
    throw new Error(json?.error ?? "Error al iniciar sesión");
  }

  return json;
}

export async function logout(accessToken: string): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
}

export async function refreshToken(refreshToken: string): Promise<RefreshResponse> {
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  const json = await res.json();
  if (!res.ok) {
    throw new Error(json?.error ?? "Error al renovar sesión");
  }

  return json;
}

export async function getMe(accessToken: string): Promise<LoginResponse["user"]> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  const json = await res.json();
  if (!res.ok) {
    throw new Error(json?.error ?? "Error al obtener usuario");
  }

  return json;
}
```

**Step 2: Modificar client.ts para incluir auth**

Modificar `frontend/src/api/client.ts`:

```tsx
import { useAuthStore } from "../store/useAuthStore";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:5001/api";

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export async function fetchWithAuth(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = {
    ...getAuthHeaders(),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  // Si 401, limpiar auth y redirigir a login
  if (res.status === 401) {
    useAuthStore.getState().clearAuth();
    window.location.href = "/login";
  }

  return res;
}

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("No se pudo consultar /health");
  return res.json();
}

async function postJson(path: string, body: Record<string, unknown>) {
  const res = await fetchWithAuth(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? "Error en solicitud");
  return data;
}

export async function wslpgDummy() {
  const res = await fetchWithAuth("/wslpg/mvp/dummy");
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? "Error en dummy");
  return data;
}

export async function wslpgUltimoNroOrden(ptoEmision: number) {
  return postJson("/wslpg/mvp/liquidacion-ultimo-nro-orden", { ptoEmision });
}

export async function wslpgLiquidacionXNroOrden(
  ptoEmision: number,
  nroOrden: number
) {
  return postJson("/wslpg/mvp/liquidacion-x-nro-orden", { ptoEmision, nroOrden });
}

export async function wslpgLiquidacionXCoe(coe: number, pdf: "S" | "N") {
  return postJson("/wslpg/mvp/liquidacion-x-coe", { coe, pdf });
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/authApi.ts frontend/src/api/client.ts
git commit -m "feat(auth): add auth API client with token interceptor

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 15: Crear componentes de layout (Navbar, ProtectedRoute)

**Files:**
- Create: `frontend/src/components/layout/Navbar.tsx`
- Create: `frontend/src/components/layout/ProtectedRoute.tsx`
- Create: `frontend/src/components/layout/index.ts`

**Step 1: Crear Navbar.tsx**

Crear `frontend/src/components/layout/Navbar.tsx`:

```tsx
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/useAuthStore";
import { logout } from "../../api/authApi";
import { useState } from "react";

export function Navbar() {
  const { user, accessToken, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const handleLogout = async () => {
    if (accessToken) {
      try {
        await logout(accessToken);
      } catch {
        // Ignorar errores de logout
      }
    }
    clearAuth();
    navigate("/login");
  };

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? "bg-green-100 text-green-700"
        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
    }`;

  return (
    <header className="bg-white border-b border-slate-200 shadow-sm">
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <div className="flex items-center">
            <Link to="/" className="flex items-center gap-2">
              <svg
                className="h-8 w-8 text-green-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="text-lg font-semibold text-slate-900">
                Liquidación Granos
              </span>
            </Link>
          </div>

          {/* Navigation Links */}
          <div className="hidden md:flex md:items-center md:gap-1">
            <NavLink to="/" className={navLinkClass} end>
              Inicio
            </NavLink>
            <NavLink to="/clientes" className={navLinkClass}>
              Clientes
            </NavLink>
            <NavLink to="/coes" className={navLinkClass}>
              COEs
            </NavLink>
            <NavLink to="/exportar" className={navLinkClass}>
              Exportar
            </NavLink>
            {user?.rol === "admin" ? (
              <NavLink to="/configuracion" className={navLinkClass}>
                Configuración
              </NavLink>
            ) : null}
          </div>

          {/* User Menu */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              <span>{user?.nombre ?? "Usuario"}</span>
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>

            {isMenuOpen ? (
              <div className="absolute right-0 mt-2 w-48 rounded-md bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5">
                <div className="px-4 py-2 text-xs text-slate-500">
                  {user?.username} ({user?.rol})
                </div>
                <hr className="my-1 border-slate-200" />
                <button
                  type="button"
                  onClick={handleLogout}
                  className="block w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-slate-100"
                >
                  Cerrar sesión
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </nav>
    </header>
  );
}
```

**Step 2: Crear ProtectedRoute.tsx**

Crear `frontend/src/components/layout/ProtectedRoute.tsx`:

```tsx
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "../../store/useAuthStore";
import { Navbar } from "./Navbar";

interface ProtectedRouteProps {
  requireAdmin?: boolean;
}

export function ProtectedRoute({ requireAdmin = false }: ProtectedRouteProps) {
  const { isAuthenticated, user } = useAuthStore();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requireAdmin && user?.rol !== "admin") {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}
```

**Step 3: Crear index.ts**

Crear `frontend/src/components/layout/index.ts`:

```tsx
export { Navbar } from "./Navbar";
export { ProtectedRoute } from "./ProtectedRoute";
```

**Step 4: Commit**

```bash
git add frontend/src/components/layout/
git commit -m "feat(ui): add layout components (Navbar, ProtectedRoute)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 16: Crear página de Login

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/index.ts`

**Step 1: Crear directorio pages**

Run: `mkdir -p frontend/src/pages`

**Step 2: Crear LoginPage.tsx**

Crear `frontend/src/pages/LoginPage.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import { Button, Input, Alert } from "../components/ui";
import { useAuthStore } from "../store/useAuthStore";
import { login } from "../api/authApi";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, setAuth } = useAuthStore();

  // Si ya está autenticado, redirigir a home
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim() || !password) {
      setError("Ingrese usuario y contraseña");
      return;
    }

    setIsLoading(true);

    try {
      const response = await login({ username: username.trim(), password });
      setAuth(response.access_token, response.user);
      // Guardar refresh token en memoria para uso futuro
      sessionStorage.setItem("refresh_token", response.refresh_token);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al iniciar sesión");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo y título */}
        <div className="text-center mb-8">
          <div className="mx-auto h-16 w-16 rounded-full bg-green-100 flex items-center justify-center mb-4">
            <svg
              className="h-10 w-10 text-green-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Liquidación de Granos
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Ingrese sus credenciales para acceder
          </p>
        </div>

        {/* Formulario */}
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Usuario"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Ingrese su usuario"
              autoComplete="username"
              disabled={isLoading}
            />

            <Input
              label="Contraseña"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Ingrese su contraseña"
              autoComplete="current-password"
              disabled={isLoading}
            />

            {error ? (
              <Alert variant="error">{error}</Alert>
            ) : null}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full"
              isLoading={isLoading}
            >
              Ingresar
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
```

**Step 3: Crear index.ts**

Crear `frontend/src/pages/index.ts`:

```tsx
export { LoginPage } from "./LoginPage";
```

**Step 4: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(ui): add LoginPage component

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 17: Configurar React Router y actualizar App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/pages/HomePage.tsx`

**Step 1: Crear HomePage placeholder**

Crear `frontend/src/pages/HomePage.tsx`:

```tsx
import { useAuthStore } from "../store/useAuthStore";

export function HomePage() {
  const { user } = useAuthStore();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-900 mb-4">
        Bienvenido, {user?.nombre}
      </h1>
      <p className="text-slate-600">
        Dashboard en construcción. Las funcionalidades estarán disponibles en próximas versiones.
      </p>
    </div>
  );
}
```

**Step 2: Exportar HomePage**

Modificar `frontend/src/pages/index.ts`:

```tsx
export { LoginPage } from "./LoginPage";
export { HomePage } from "./HomePage";
```

**Step 3: Actualizar App.tsx con rutas**

Modificar `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ProtectedRoute } from "./components/layout";
import { LoginPage, HomePage } from "./pages";
import ClientsPage from "./ClientsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Ruta pública */}
        <Route path="/login" element={<LoginPage />} />

        {/* Rutas protegidas */}
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/clientes" element={<ClientsPage />} />
          {/* Placeholders para rutas futuras */}
          <Route path="/coes" element={<div>COEs - Próximamente</div>} />
          <Route path="/exportar" element={<div>Exportar - Próximamente</div>} />
        </Route>

        {/* Rutas admin */}
        <Route element={<ProtectedRoute requireAdmin />}>
          <Route path="/configuracion" element={<div>Configuración - Próximamente</div>} />
          <Route path="/configuracion/usuarios" element={<div>Usuarios - Próximamente</div>} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

**Step 4: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: Build exitoso sin errores

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/
git commit -m "feat(ui): configure React Router with protected routes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 18: Ejecutar todos los tests y verificar

**Step 1: Ejecutar tests de backend**

Run: `cd backend && pytest -v`
Expected: Todos los tests pasan

**Step 2: Verificar build de frontend**

Run: `cd frontend && npm run build`
Expected: Build exitoso

**Step 3: Verificar TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: Sin errores de tipos

**Step 4: Commit final si hay cambios pendientes**

```bash
git status
# Si hay cambios:
git add .
git commit -m "chore: fix any remaining issues

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 19: Push y crear PR

**Step 1: Push de la rama**

Run: `git push -u origin feature/003-auth-login`

**Step 2: Crear PR a dev**

```bash
gh pr create --base dev --head feature/003-auth-login --title "feat: add authentication system and login UI" --body "$(cat <<'EOF'
## Summary
- Backend: User model, JWT auth endpoints, bcrypt passwords, Redis token blacklist, rate limiting
- Frontend: React Router v6, Login page, Navbar, ProtectedRoute, Zustand auth store
- UI components: Button, Input, Alert, Spinner with green theme

## Test plan
- [x] Unit tests for auth service (password hashing, JWT tokens)
- [x] Unit tests for token blacklist
- [x] Integration tests for auth API (login, logout, me, refresh)
- [x] Frontend TypeScript compiles
- [x] Frontend builds successfully

## Security measures
- JWT with 15min expiration + 7-day refresh token
- Bcrypt cost factor 12 for password hashing
- Rate limiting on login (5/min per IP)
- Token blacklist on logout via Redis
- Access token in memory only (not localStorage)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Resumen de archivos creados/modificados

### Backend (nuevos)
- `backend/app/models/user.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/token_blacklist.py`
- `backend/app/middleware/__init__.py`
- `backend/app/middleware/auth_middleware.py`
- `backend/app/api/auth.py`
- `backend/app/cli.py`
- `backend/tests/unit/test_auth_service.py`
- `backend/tests/unit/test_token_blacklist.py`
- `backend/tests/integration/test_auth_api.py`
- `backend/migrations/versions/xxx_add_users_table.py`

### Backend (modificados)
- `backend/requirements.txt`
- `backend/app/models/__init__.py`
- `backend/app/api/__init__.py`
- `backend/app/__init__.py`
- `backend/app/config.py`

### Frontend (nuevos)
- `frontend/src/components/ui/Button.tsx`
- `frontend/src/components/ui/Input.tsx`
- `frontend/src/components/ui/Alert.tsx`
- `frontend/src/components/ui/Spinner.tsx`
- `frontend/src/components/ui/index.ts`
- `frontend/src/components/layout/Navbar.tsx`
- `frontend/src/components/layout/ProtectedRoute.tsx`
- `frontend/src/components/layout/index.ts`
- `frontend/src/store/useAuthStore.ts`
- `frontend/src/api/authApi.ts`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/pages/index.ts`

### Frontend (modificados)
- `frontend/index.html`
- `frontend/tailwind.config.cjs`
- `frontend/package.json`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
