from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from flask import current_app, has_app_context
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .certificate_validator import validate_certificate_and_key


def _base_path() -> Path:
    if has_app_context():
        base = current_app.config.get("CLIENT_CERTIFICATES_BASE_PATH")
    else:
        base = os.getenv("CLIENT_CERTIFICATES_BASE_PATH", "/app/certificados_clientes")
    return Path(str(base))


def _client_dir(client_id: int) -> Path:
    return _base_path() / str(client_id)


def save_client_certificates(
    client_id: int,
    cert_file: FileStorage,
    key_file: FileStorage,
) -> dict:
    cert_filename = secure_filename(cert_file.filename or "")
    key_filename = secure_filename(key_file.filename or "")
    if not cert_filename:
        raise ValueError("El archivo cert_file es obligatorio.")
    if not key_filename:
        raise ValueError("El archivo key_file es obligatorio.")

    cert_bytes = cert_file.read()
    key_bytes = key_file.read()

    validate_certificate_and_key(cert_bytes, key_bytes)

    client_directory = _client_dir(client_id)
    client_directory.mkdir(parents=True, exist_ok=True)

    cert_path = client_directory / "cert.crt"
    key_path = client_directory / "private.key"

    cert_path.write_bytes(cert_bytes)
    key_path.write_bytes(key_bytes)

    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass

    return {
        "cert_crt_path": str(cert_path),
        "cert_key_path": str(key_path),
        "cert_crt_filename": cert_filename,
        "cert_key_filename": key_filename,
    }


def delete_client_certificates(client_id: int) -> None:
    directory = _client_dir(client_id)
    if directory.exists():
        shutil.rmtree(directory)


def get_client_certificate_meta(client_id: int) -> dict:
    directory = _client_dir(client_id)
    cert_path = directory / "cert.crt"
    key_path = directory / "private.key"

    cert_exists = cert_path.is_file()
    key_exists = key_path.is_file()

    uploaded_at = None
    if cert_exists and key_exists:
        timestamp = max(cert_path.stat().st_mtime, key_path.stat().st_mtime)
        uploaded_at = datetime.utcfromtimestamp(timestamp).isoformat()

    return {
        "base_path": str(_base_path()),
        "client_path": str(directory),
        "cert_crt_path": str(cert_path),
        "cert_key_path": str(key_path),
        "cert_crt_exists": cert_exists,
        "cert_key_exists": key_exists,
        "has_certificates": cert_exists and key_exists,
        "cert_crt_size": cert_path.stat().st_size if cert_exists else None,
        "cert_key_size": key_path.stat().st_size if key_exists else None,
        "detected_uploaded_at": uploaded_at,
    }
