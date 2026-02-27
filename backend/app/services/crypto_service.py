from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, has_app_context

PLACEHOLDER_FISCAL_SECRET = "PENDIENTE_ACTUALIZACION_UI"


def _resolve_raw_key() -> str:
    if has_app_context():
        return str(
            current_app.config.get("CLIENT_SECRET_KEY")
            or current_app.config.get("SECRET_KEY")
            or "dev-secret"
        )
    return os.getenv("CLIENT_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret"


@lru_cache(maxsize=32)
def _build_fernet(raw_key: str) -> Fernet:
    key_bytes = raw_key.encode("utf-8")

    try:
        return Fernet(key_bytes)
    except Exception:
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
        return Fernet(derived_key)


def _get_fernet() -> Fernet:
    return _build_fernet(_resolve_raw_key())


def encrypt_secret(plain: str) -> str:
    value = str(plain or "").strip()
    if not value:
        raise ValueError("La clave fiscal no puede estar vacia.")

    token = _get_fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(cipher: str) -> str:
    value = str(cipher or "").strip()
    if not value:
        raise ValueError("El secreto cifrado no puede estar vacio.")

    try:
        plain = _get_fernet().decrypt(value.encode("utf-8"))
        return plain.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("No se pudo descifrar el secreto.") from exc


def is_placeholder_secret(cipher: str) -> bool:
    try:
        return decrypt_secret(cipher) == PLACEHOLDER_FISCAL_SECRET
    except ValueError:
        return False
