from __future__ import annotations

import pytest

from app.services.crypto_service import decrypt_secret, encrypt_secret


def test_encrypt_decrypt_roundtrip(app):
    with app.app_context():
        cipher = encrypt_secret("super-secreto-123")

    assert cipher != "super-secreto-123"

    with app.app_context():
        plain = decrypt_secret(cipher)

    assert plain == "super-secreto-123"


def test_decrypt_invalid_secret_raises(app):
    with app.app_context():
        with pytest.raises(ValueError):
            decrypt_secret("valor-invalido")
