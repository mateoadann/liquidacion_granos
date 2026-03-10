from __future__ import annotations

from app.extensions import db
from app.models import User


def _create_user(*, username: str, nombre: str, rol: str = "usuario") -> User:
    user = User()
    user.username = username
    user.nombre = nombre
    user.rol = rol
    user.set_password("password123")
    user.activo = True
    db.session.add(user)
    db.session.commit()
    return user


def test_list_users_empty(client, admin_headers):
    response = client.get("/api/users", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["users"] == []


def test_list_users_returns_data(client, admin_headers):
    _create_user(username="user1", nombre="Usuario 1")
    _create_user(username="user2", nombre="Usuario 2")

    response = client.get("/api/users", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["users"]) == 2


def test_get_user_detail(client, admin_headers):
    user = _create_user(username="testuser", nombre="Test User", rol="admin")

    response = client.get(f"/api/users/{user.id}", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["username"] == "testuser"
    assert data["nombre"] == "Test User"
    assert data["rol"] == "admin"
    assert "password_hash" not in data


def test_get_user_not_found(client, admin_headers):
    response = client.get("/api/users/99999", headers=admin_headers)
    assert response.status_code == 404


def test_create_user(client, admin_headers):
    response = client.post("/api/users", json={
        "username": "newuser",
        "nombre": "New User",
        "password": "securepass123",
        "rol": "usuario"
    }, headers=admin_headers)
    assert response.status_code == 201
    data = response.get_json()
    assert data["username"] == "newuser"


def test_create_user_duplicate_username(client, admin_headers):
    _create_user(username="existing", nombre="Existing")

    response = client.post("/api/users", json={
        "username": "existing",
        "nombre": "New User",
        "password": "securepass123"
    }, headers=admin_headers)
    assert response.status_code == 409


def test_update_user(client, admin_headers):
    user = _create_user(username="updateme", nombre="Old Name")

    response = client.patch(f"/api/users/{user.id}", json={
        "nombre": "New Name"
    }, headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["nombre"] == "New Name"


def test_cannot_deactivate_last_admin(client, admin_headers):
    admin = _create_user(username="soloadmin", nombre="Solo Admin", rol="admin")

    response = client.patch(f"/api/users/{admin.id}", json={
        "activo": False
    }, headers=admin_headers)
    assert response.status_code == 400
    assert "último admin" in response.get_json()["error"].lower()


def test_cannot_change_last_admin_role(client, admin_headers):
    admin = _create_user(username="soloadmin", nombre="Solo Admin", rol="admin")

    response = client.patch(f"/api/users/{admin.id}", json={
        "rol": "usuario"
    }, headers=admin_headers)
    assert response.status_code == 400
    assert "último admin" in response.get_json()["error"].lower()


def test_delete_user(client, admin_headers):
    user = _create_user(username="deleteme", nombre="Delete Me")

    response = client.delete(f"/api/users/{user.id}", headers=admin_headers)
    assert response.status_code == 204


def test_cannot_delete_last_admin(client, admin_headers):
    admin = _create_user(username="soloadmin", nombre="Solo Admin", rol="admin")

    response = client.delete(f"/api/users/{admin.id}", headers=admin_headers)
    assert response.status_code == 400


def test_reset_password(client, admin_headers):
    user = _create_user(username="resetme", nombre="Reset Me")

    response = client.post(f"/api/users/{user.id}/reset-password", json={
        "new_password": "newpassword123"
    }, headers=admin_headers)
    assert response.status_code == 200
