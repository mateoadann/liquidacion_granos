from __future__ import annotations

import pytest

from app.extensions import db
from app.models.lpg_document import LpgDocument
from app.models.taxpayer import Taxpayer

API_KEY = "test-integration-key"


@pytest.fixture()
def api_headers():
    return {"X-API-Key": API_KEY}


def _create_doc(coe: str = "33020030787127") -> LpgDocument:
    tp = Taxpayer()
    tp.cuit = "30711165378"
    tp.empresa = "Test SA"
    tp.cuit_representado = "30711165378"
    tp.cert_crt_path = "/tmp/test.crt"
    tp.cert_key_path = "/tmp/test.key"
    tp.clave_fiscal_encrypted = "x"
    tp.activo = True
    db.session.add(tp)
    db.session.commit()

    doc = LpgDocument()
    doc.taxpayer_id = tp.id
    doc.coe = coe
    doc.tipo_documento = "LPG"
    doc.raw_data = {}
    db.session.add(doc)
    db.session.commit()
    return doc


def test_control_requires_api_key(client):
    resp = client.post("/api/v1/coes/control", json={"coe": "1", "estado": "ok"})
    assert resp.status_code == 401


def test_control_invalid_estado_422(client, api_headers):
    resp = client.post(
        "/api/v1/coes/control",
        json={"coe": "1", "estado": "raro"},
        headers=api_headers,
    )
    assert resp.status_code == 422


def test_control_coe_not_found_404(client, api_headers):
    resp = client.post(
        "/api/v1/coes/control",
        json={"coe": "99999999999999", "estado": "ok"},
        headers=api_headers,
    )
    assert resp.status_code == 404


def test_control_ok_persists(client, app, api_headers):
    with app.app_context():
        _create_doc(coe="33020030787127")

    resp = client.post(
        "/api/v1/coes/control",
        json={
            "coe": "33020030787127",
            "estado": "ok",
            "controlado_en": "2026-06-30T10:41:37-03:00",
        },
        headers=api_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["control_rpa_estado"] == "ok"

    with app.app_context():
        doc = LpgDocument.query.filter_by(coe="33020030787127").first()
        assert doc.control_rpa_estado == "ok"
        assert doc.control_rpa_en is not None


def test_control_inconsistente_persists(client, app, api_headers):
    with app.app_context():
        _create_doc(coe="33020030787128")

    resp = client.post(
        "/api/v1/coes/control",
        json={"coe": "33020030787128", "estado": "inconsistente"},
        headers=api_headers,
    )
    assert resp.status_code == 200

    with app.app_context():
        doc = LpgDocument.query.filter_by(coe="33020030787128").first()
        assert doc.control_rpa_estado == "inconsistente"
