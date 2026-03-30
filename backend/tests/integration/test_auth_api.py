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
