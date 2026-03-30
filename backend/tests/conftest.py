from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.time_utils import now_cordoba_aware
from app.services.auth_service import create_access_token
from app.services.token_blacklist import _reset_for_testing


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test-secret"
    CLIENT_SECRET_KEY = "test-client-secret"
    CORS_ORIGINS = ["http://localhost:5173"]
    # No incluir REDIS_URL - se usará fallback en memoria


@pytest.fixture()
def app(tmp_path):
    class Config(TestConfig):
        CLIENT_CERTIFICATES_BASE_PATH = str(tmp_path / "certificados_clientes")

    # Reset token blacklist para usar memoria
    _reset_for_testing()

    application = create_app(Config)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers():
    """Headers con JWT de usuario autenticado (rol usuario)."""
    token = create_access_token(user_id=999, username="testuser", rol="usuario")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers():
    """Headers con JWT de usuario admin."""
    token = create_access_token(user_id=1, username="admin", rol="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def cert_pair_bytes():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Tests"),
            x509.NameAttribute(NameOID.COMMON_NAME, "test.local"),
        ]
    )

    now = now_cordoba_aware()
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )

    cert_bytes = certificate.public_bytes(serialization.Encoding.PEM)
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_bytes, key_bytes


@pytest.fixture()
def mismatched_private_key_bytes():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
