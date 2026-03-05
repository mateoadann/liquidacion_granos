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
