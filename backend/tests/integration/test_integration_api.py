from __future__ import annotations

import pytest

from app.extensions import db
from app.models.coe_estado import CoeEstado

API_KEY = "test-integration-key"


@pytest.fixture()
def api_headers():
    return {"X-API-Key": API_KEY}


def _create_coe_estado(
    coe="33020030787127",
    estado="descargado",
    cuit_empresa="30711165378",
    hash_payload_emitido="sha256:abc123",
):
    entry = CoeEstado(
        coe=coe,
        cuit_empresa=cuit_empresa,
        estado=estado,
        hash_payload_emitido=hash_payload_emitido,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


# -----------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------


def test_health_no_auth(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "timestamp" in data


# -----------------------------------------------------------------------
# POST /v1/coes/cargado — auth
# -----------------------------------------------------------------------


def test_post_cargado_requires_api_key(client):
    resp = client.post("/api/v1/coes/cargado", json={"coe": "123"})
    assert resp.status_code == 401


def test_post_cargado_invalid_api_key(client):
    resp = client.post(
        "/api/v1/coes/cargado",
        json={"coe": "123"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


# -----------------------------------------------------------------------
# POST /v1/coes/cargado — validation
# -----------------------------------------------------------------------


def test_post_cargado_validation_missing_fields(client, api_headers):
    resp = client.post("/api/v1/coes/cargado", json={}, headers=api_headers)
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["error"] == "validacion_fallida"


# -----------------------------------------------------------------------
# POST /v1/coes/cargado — success
# -----------------------------------------------------------------------


def test_post_cargado_success(client, app, api_headers):
    with app.app_context():
        _create_coe_estado(
            coe="33020030787127",
            estado="descargado",
            hash_payload_emitido="sha256:abc123",
        )

    resp = client.post(
        "/api/v1/coes/cargado",
        json={
            "coe": "33020030787127",
            "estado": "ok",
            "ejecucion_id": "exec-001",
            "usuario": "robot",
            "cargado_en": "2026-04-22T10:00:00",
            "hash_payload": "sha256:abc123",
            "comprobante": {"codigo": "123", "tipo_pto_vta": 1, "nro": 42, "fecha_emision": "2026-04-22"},
        },
        headers=api_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["estado"] == "cargado"
    assert data["duplicado"] is False


# -----------------------------------------------------------------------
# POST /v1/coes/cargado — hash mismatch 409
# -----------------------------------------------------------------------


def test_post_cargado_hash_mismatch_409(client, app, api_headers):
    with app.app_context():
        _create_coe_estado(
            coe="33020030787128",
            estado="descargado",
            hash_payload_emitido="sha256:original",
        )

    resp = client.post(
        "/api/v1/coes/cargado",
        json={
            "coe": "33020030787128",
            "estado": "ok",
            "ejecucion_id": "exec-002",
            "usuario": "robot",
            "cargado_en": "2026-04-22T10:00:00",
            "hash_payload": "sha256:different",
            "comprobante": {"codigo": "123"},
        },
        headers=api_headers,
    )
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error"] == "payload_mismatch"


# -----------------------------------------------------------------------
# POST /v1/coes/cargado — transicion invalida 409
# -----------------------------------------------------------------------


def test_post_cargado_transicion_invalida_409(client, app, api_headers):
    with app.app_context():
        _create_coe_estado(
            coe="33020030787129",
            estado="pendiente",
            hash_payload_emitido="sha256:abc123",
        )

    resp = client.post(
        "/api/v1/coes/cargado",
        json={
            "coe": "33020030787129",
            "estado": "ok",
            "ejecucion_id": "exec-003",
            "usuario": "robot",
            "cargado_en": "2026-04-22T10:00:00",
            "hash_payload": "sha256:abc123",
            "comprobante": {"codigo": "123"},
        },
        headers=api_headers,
    )
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error"] == "transicion_invalida"


# -----------------------------------------------------------------------
# GET /v1/coes/<coe>
# -----------------------------------------------------------------------


def test_get_coe_estado_success(client, app, api_headers):
    with app.app_context():
        _create_coe_estado(coe="33020030787130", estado="pendiente")

    resp = client.get("/api/v1/coes/33020030787130", headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["coe"] == "33020030787130"
    assert data["estado"] == "pendiente"


def test_get_coe_not_found_404(client, api_headers):
    resp = client.get("/api/v1/coes/99999999999999", headers=api_headers)
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "coe_no_encontrado"


# -----------------------------------------------------------------------
# GET /v1/coes/estados
# -----------------------------------------------------------------------


def test_list_estados_success(client, app, api_headers):
    with app.app_context():
        _create_coe_estado(coe="33020030787131", estado="pendiente")
        _create_coe_estado(coe="33020030787132", estado="descargado")

    resp = client.get("/api/v1/coes/estados", headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_estados_filter_by_estado(client, app, api_headers):
    with app.app_context():
        _create_coe_estado(coe="33020030787133", estado="pendiente")
        _create_coe_estado(coe="33020030787134", estado="descargado")
        _create_coe_estado(coe="33020030787135", estado="pendiente")

    resp = client.get("/api/v1/coes/estados?estado=pendiente", headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    assert all(item["estado"] == "pendiente" for item in data["items"])
