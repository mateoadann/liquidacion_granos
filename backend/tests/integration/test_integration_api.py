from __future__ import annotations

import pytest

from app.extensions import db
from app.models.coe_estado import CoeEstado

API_KEY = "test-integration-key"
ADMIN_TOKEN = "test-admin-token"


@pytest.fixture()
def api_headers():
    return {"X-API-Key": API_KEY}


@pytest.fixture()
def admin_api_headers():
    return {"X-API-Key": API_KEY, "X-Admin-Token": ADMIN_TOKEN}


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


# -----------------------------------------------------------------------
# POST /v1/coes/<coe>/forzar-sincronizado
# -----------------------------------------------------------------------


def _valid_forzar_body(**overrides):
    body = {
        "estado": "cargado",
        "razon": "JSON editado a mano para test",
        "usuario": "mateo.adan",
        "forzado_en": "2026-04-30T09:00:00",
        "hash_payload_local": "sha256:local_hash",
        "comprobante": {
            "codigo": "F1",
            "tipo_pto_vta": 3301,
            "nro": 1872,
            "fecha_emision": "2025-11-07",
        },
        "ejecucion_id": "run_test_001",
        "cargado_en": "2026-04-29T14:11:49",
    }
    body.update(overrides)
    return body


def test_forzar_sin_admin_token_devuelve_403(client, app, api_headers):
    with app.app_context():
        _create_coe_estado(coe="33099900000001", estado="descargado")

    resp = client.post(
        "/api/v1/coes/33099900000001/forzar-sincronizado",
        json=_valid_forzar_body(),
        headers=api_headers,  # solo X-API-Key, sin X-Admin-Token
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["error"] == "admin_token_invalido"


def test_forzar_con_admin_token_invalido_devuelve_403(client, app):
    with app.app_context():
        _create_coe_estado(coe="33099900000002", estado="descargado")

    resp = client.post(
        "/api/v1/coes/33099900000002/forzar-sincronizado",
        json=_valid_forzar_body(),
        headers={"X-API-Key": API_KEY, "X-Admin-Token": "wrong-token"},
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["error"] == "admin_token_invalido"


def test_forzar_sin_api_key_devuelve_401(client, app):
    with app.app_context():
        _create_coe_estado(coe="33099900000003", estado="descargado")

    resp = client.post(
        "/api/v1/coes/33099900000003/forzar-sincronizado",
        json=_valid_forzar_body(),
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "api_key_invalida"


def test_forzar_coe_inexistente_devuelve_404(client, admin_api_headers):
    resp = client.post(
        "/api/v1/coes/99999999999999/forzar-sincronizado",
        json=_valid_forzar_body(),
        headers=admin_api_headers,
    )
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "coe_no_encontrado"


def test_forzar_desde_descargado_a_cargado_actualiza_estado_y_audit(
    client, app, admin_api_headers
):
    coe = "33099900000010"
    with app.app_context():
        _create_coe_estado(
            coe=coe,
            estado="descargado",
            hash_payload_emitido="sha256:emitido_hash",
        )

    resp = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=_valid_forzar_body(),
        headers=admin_api_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["coe"] == coe
    assert data["estado_anterior"] == "descargado"
    assert data["estado_nuevo"] == "cargado"
    assert data["duplicado"] is False

    with app.app_context():
        entry = CoeEstado.query.filter_by(coe=coe).first()
        assert entry.estado == "cargado"
        assert entry.forzado_en is not None
        assert entry.forzado_por == "mateo.adan"
        assert entry.forzado_razon == "JSON editado a mano para test"
        assert entry.forzado_estado_previo == "descargado"
        assert entry.hash_payload_forzado == "sha256:local_hash"
        # hash_payload_emitido NO se toca
        assert entry.hash_payload_emitido == "sha256:emitido_hash"


def test_forzar_desde_cargado_a_cargado_misma_razon_es_duplicado(
    client, app, admin_api_headers
):
    coe = "33099900000011"
    with app.app_context():
        _create_coe_estado(coe=coe, estado="descargado")

    body = _valid_forzar_body()
    # Primera llamada
    resp1 = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=body,
        headers=admin_api_headers,
    )
    assert resp1.status_code == 200
    assert resp1.get_json()["duplicado"] is False

    # Segunda llamada idéntica
    resp2 = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=body,
        headers=admin_api_headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["duplicado"] is True
    assert data2["estado_nuevo"] == "cargado"


def test_forzar_desde_cargado_a_cargado_distinta_razon_actualiza_y_no_duplicado(
    client, app, admin_api_headers
):
    coe = "33099900000012"
    with app.app_context():
        _create_coe_estado(coe=coe, estado="descargado")

    # Primera llamada
    resp1 = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=_valid_forzar_body(razon="Primera razón válida"),
        headers=admin_api_headers,
    )
    assert resp1.status_code == 200

    # Segunda con distinta razón
    resp2 = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=_valid_forzar_body(razon="Segunda razón completamente distinta"),
        headers=admin_api_headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["duplicado"] is False

    with app.app_context():
        entry = CoeEstado.query.filter_by(coe=coe).first()
        assert entry.forzado_razon == "Segunda razón completamente distinta"


def test_forzar_desde_error_a_cargado_actualiza_y_limpia_error_fields(
    client, app, admin_api_headers
):
    coe = "33099900000013"
    with app.app_context():
        entry = _create_coe_estado(coe=coe, estado="error")
        entry.error_fase = "F11"
        entry.error_mensaje = "Crash de Holistor"
        db.session.commit()

    resp = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=_valid_forzar_body(),
        headers=admin_api_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["estado_anterior"] == "error"
    assert data["estado_nuevo"] == "cargado"

    with app.app_context():
        entry = CoeEstado.query.filter_by(coe=coe).first()
        assert entry.estado == "cargado"
        assert entry.error_fase is None
        assert entry.error_mensaje is None
        assert entry.forzado_estado_previo == "error"


def test_forzar_a_error_requiere_error_fase_y_mensaje(
    client, app, admin_api_headers
):
    coe = "33099900000014"
    with app.app_context():
        _create_coe_estado(coe=coe, estado="descargado")

    body = _valid_forzar_body()
    body["estado"] = "error"
    # Sin error_fase ni error_mensaje, también remover campos cargado-only
    body.pop("comprobante", None)
    body.pop("ejecucion_id", None)
    body.pop("cargado_en", None)

    resp = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=body,
        headers=admin_api_headers,
    )
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["error"] == "validacion_fallida"
    assert "error_fase" in data["mensaje"]


def test_forzar_persiste_hash_payload_local_en_hash_payload_forzado(
    client, app, admin_api_headers
):
    coe = "33099900000015"
    with app.app_context():
        _create_coe_estado(coe=coe, estado="descargado")

    resp = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=_valid_forzar_body(hash_payload_local="sha256:hash_distintivo_xyz"),
        headers=admin_api_headers,
    )
    assert resp.status_code == 200

    with app.app_context():
        entry = CoeEstado.query.filter_by(coe=coe).first()
        assert entry.hash_payload_forzado == "sha256:hash_distintivo_xyz"


def test_forzar_no_modifica_hash_payload_emitido(client, app, admin_api_headers):
    coe = "33099900000016"
    with app.app_context():
        _create_coe_estado(
            coe=coe,
            estado="descargado",
            hash_payload_emitido="sha256:emitido_intacto",
        )

    resp = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=_valid_forzar_body(hash_payload_local="sha256:local_diferente"),
        headers=admin_api_headers,
    )
    assert resp.status_code == 200

    with app.app_context():
        entry = CoeEstado.query.filter_by(coe=coe).first()
        assert entry.hash_payload_emitido == "sha256:emitido_intacto"
        assert entry.hash_payload_forzado == "sha256:local_diferente"


def test_forzar_desde_pendiente_a_cargado(client, app, admin_api_headers):
    coe = "33099900000017"
    with app.app_context():
        _create_coe_estado(coe=coe, estado="pendiente")

    resp = client.post(
        f"/api/v1/coes/{coe}/forzar-sincronizado",
        json=_valid_forzar_body(),
        headers=admin_api_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["estado_anterior"] == "pendiente"
    assert data["estado_nuevo"] == "cargado"

    with app.app_context():
        entry = CoeEstado.query.filter_by(coe=coe).first()
        assert entry.estado == "cargado"
        assert entry.forzado_estado_previo == "pendiente"
