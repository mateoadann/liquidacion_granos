"""Integration tests for GET /clients/<id>/clave-fiscal.

Covers:
- 200 happy path: encrypted key → decrypted value returned + AuditEvent persisted.
- 409 when client has no key (empty string).
- 409 when client has placeholder key.
- 404 for unknown client id.
- 401 when request is made without auth token.
"""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models import AuditEvent, Taxpayer
from app.services.crypto_service import PLACEHOLDER_FISCAL_SECRET, encrypt_secret


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def taxpayer_with_key(app):
    """Taxpayer with a real encrypted fiscal key."""
    with app.app_context():
        plain = "mi-clave-super-secreta"
        tp = Taxpayer()
        tp.empresa = "Test Empresa"
        tp.cuit = "20123456789"
        tp.cuit_representado = "20123456789"
        tp.clave_fiscal_encrypted = encrypt_secret(plain)
        tp.activo = True
        db.session.add(tp)
        db.session.commit()
        yield tp.id, plain


@pytest.fixture()
def taxpayer_no_key(app):
    """Taxpayer with an empty fiscal key field."""
    with app.app_context():
        tp = Taxpayer()
        tp.empresa = "Sin Clave SA"
        tp.cuit = "20987654321"
        tp.cuit_representado = "20987654321"
        tp.clave_fiscal_encrypted = ""
        tp.activo = True
        db.session.add(tp)
        db.session.commit()
        yield tp.id


@pytest.fixture()
def taxpayer_placeholder_key(app):
    """Taxpayer whose fiscal key is the PLACEHOLDER sentinel."""
    with app.app_context():
        tp = Taxpayer()
        tp.empresa = "Placeholder SA"
        tp.cuit = "20111111111"
        tp.cuit_representado = "20111111111"
        tp.clave_fiscal_encrypted = encrypt_secret(PLACEHOLDER_FISCAL_SECRET)
        tp.activo = True
        db.session.add(tp)
        db.session.commit()
        yield tp.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestClaveFiscalHappyPath:
    def test_returns_200_with_decrypted_value(self, client, auth_headers, taxpayer_with_key):
        taxpayer_id, plain = taxpayer_with_key
        res = client.get(f"/api/clients/{taxpayer_id}/clave-fiscal", headers=auth_headers)

        assert res.status_code == 200
        data = res.get_json()
        assert data["clave_fiscal"] == plain

    def test_audit_event_created(self, client, auth_headers, taxpayer_with_key, app):
        taxpayer_id, _ = taxpayer_with_key

        with app.app_context():
            count_before = db.session.query(AuditEvent).count()

        client.get(f"/api/clients/{taxpayer_id}/clave-fiscal", headers=auth_headers)

        with app.app_context():
            events = (
                db.session.query(AuditEvent)
                .filter(
                    AuditEvent.taxpayer_id == taxpayer_id,
                    AuditEvent.operation == "clave_fiscal_copiada",
                )
                .all()
            )
            assert len(events) == 1
            assert db.session.query(AuditEvent).count() == count_before + 1

    def test_audit_event_has_correct_fields(self, client, auth_headers, taxpayer_with_key, app):
        taxpayer_id, _ = taxpayer_with_key
        client.get(f"/api/clients/{taxpayer_id}/clave-fiscal", headers=auth_headers)

        with app.app_context():
            event = (
                db.session.query(AuditEvent)
                .filter(
                    AuditEvent.taxpayer_id == taxpayer_id,
                    AuditEvent.operation == "clave_fiscal_copiada",
                )
                .first()
            )
            assert event is not None
            assert event.taxpayer_id == taxpayer_id
            assert event.level == "info"
            meta = event.metadata_json or {}
            assert meta.get("by_username") == "testuser"
            assert meta.get("by_user_id") == 999


class TestClaveFiscalNotFound:
    def test_unknown_id_returns_404(self, client, auth_headers):
        res = client.get("/api/clients/99999/clave-fiscal", headers=auth_headers)
        assert res.status_code == 404
        assert "error" in res.get_json()

    def test_no_audit_event_created_for_unknown_id(self, client, auth_headers, app):
        with app.app_context():
            count_before = db.session.query(AuditEvent).count()

        client.get("/api/clients/99999/clave-fiscal", headers=auth_headers)

        with app.app_context():
            assert db.session.query(AuditEvent).count() == count_before


class TestClaveFiscalNoKey:
    def test_empty_key_returns_409(self, client, auth_headers, taxpayer_no_key):
        res = client.get(f"/api/clients/{taxpayer_no_key}/clave-fiscal", headers=auth_headers)
        assert res.status_code == 409
        data = res.get_json()
        assert "error" in data
        assert "clave fiscal" in data["error"].lower()

    def test_no_audit_event_for_empty_key(self, client, auth_headers, taxpayer_no_key, app):
        with app.app_context():
            count_before = db.session.query(AuditEvent).count()

        client.get(f"/api/clients/{taxpayer_no_key}/clave-fiscal", headers=auth_headers)

        with app.app_context():
            assert db.session.query(AuditEvent).count() == count_before

    def test_placeholder_key_returns_409(self, client, auth_headers, taxpayer_placeholder_key):
        res = client.get(
            f"/api/clients/{taxpayer_placeholder_key}/clave-fiscal", headers=auth_headers
        )
        assert res.status_code == 409
        data = res.get_json()
        assert "error" in data

    def test_no_audit_event_for_placeholder_key(
        self, client, auth_headers, taxpayer_placeholder_key, app
    ):
        with app.app_context():
            count_before = db.session.query(AuditEvent).count()

        client.get(
            f"/api/clients/{taxpayer_placeholder_key}/clave-fiscal", headers=auth_headers
        )

        with app.app_context():
            assert db.session.query(AuditEvent).count() == count_before


class TestClaveFiscalRequiresAuth:
    def test_no_token_returns_401(self, client, taxpayer_with_key):
        taxpayer_id, _ = taxpayer_with_key
        res = client.get(f"/api/clients/{taxpayer_id}/clave-fiscal")
        assert res.status_code == 401

    def test_invalid_token_returns_401(self, client, taxpayer_with_key):
        taxpayer_id, _ = taxpayer_with_key
        res = client.get(
            f"/api/clients/{taxpayer_id}/clave-fiscal",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert res.status_code == 401
