"""Tests de la API de gestiones de datos faltantes (SPEC §8.8)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.gestion_id import calcular_gestion_id

API_KEY = "test-integration-key"
URL = "/api/v1/gestiones"


@pytest.fixture()
def api_headers():
    return {"X-API-Key": API_KEY}


def _gestion(gestion_id=None, tipo="alta_cliente", cuit_empresa="30711165378", identificador="30708729929", **kw):
    gid = gestion_id or calcular_gestion_id(tipo, cuit_empresa, identificador)
    base = {
        "gestion_id": gid,
        "tipo": tipo,
        "cuit_empresa": cuit_empresa,
        "razon_social": "Manassero Hnos SRL",
        "identificador": identificador,
        "descripcion": f"Alta {identificador} en Manassero Hnos SRL",
        "datos_contexto": {"cuit": identificador},
        "coes_afectados": ["33023150836200"],
        "detectado_en": "2026-06-25T10:30:00-03:00",
    }
    base.update(kw)
    return base


def _post_batch(client, api_headers, gestiones):
    return client.post(URL, json={"reportado_en": "2026-06-25T10:30:00-03:00", "gestiones": gestiones}, headers=api_headers)


# ---------------------------------------------------------------------------
# POST creación
# ---------------------------------------------------------------------------


def test_post_gestiones_crea_pendiente(client, api_headers):
    g = _gestion()
    resp = _post_batch(client, api_headers, [g])
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["recibidas"] == 1
    assert data["creadas"] == 1
    assert data["actualizadas"] == 0
    assert data["resultados"][0] == {"gestion_id": g["gestion_id"], "accion": "creada", "duplicado": False}

    # Quedó en pendiente
    listado = client.get(URL, headers=api_headers).get_json()
    assert listado["gestiones"][0]["estado"] == "pendiente"


def test_post_gestiones_idempotente_refresca_metadata_no_estado(client, api_headers):
    g = _gestion()
    _post_batch(client, api_headers, [g])
    # Marca realizada vía el servicio para que el estado NO sea pendiente
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"], usuario="ana.estudio")

    # Re-POST con metadata cambiada
    g2 = _gestion(descripcion="DESC NUEVA", coes_afectados=["99999999999999"])
    resp = _post_batch(client, api_headers, [g2])
    data = resp.get_json()
    assert data["creadas"] == 0
    assert data["actualizadas"] == 1
    assert data["resultados"][0]["duplicado"] is True

    fila = client.get(URL, headers=api_headers).get_json()["gestiones"][0]
    assert fila["descripcion"] == "DESC NUEVA"
    assert fila["coes_afectados"] == ["99999999999999"]
    assert fila["estado"] == "realizada"  # NO regresó a pendiente


def test_post_gestiones_batch_mixto_creadas_y_actualizadas(client, api_headers):
    g1 = _gestion(identificador="30708729929")
    _post_batch(client, api_headers, [g1])

    g2 = _gestion(tipo="mapeo_grano", identificador="23", descripcion="Mapear grano 23")
    resp = _post_batch(client, api_headers, [g1, g2])  # g1 existente, g2 nuevo
    data = resp.get_json()
    assert data["recibidas"] == 2
    assert data["creadas"] == 1
    assert data["actualizadas"] == 1


def test_post_gestiones_duplicado_intra_batch_no_revienta(client, api_headers):
    """Mismo gestion_id dos veces en un lote → dedup, no IntegrityError. (review C1)"""
    g1 = _gestion(descripcion="primera", coes_afectados=["11111111111111"])
    g2 = _gestion(descripcion="segunda (gana)", coes_afectados=["22222222222222"])  # mismo gestion_id
    assert g1["gestion_id"] == g2["gestion_id"]

    resp = _post_batch(client, api_headers, [g1, g2])
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["recibidas"] == 1  # deduplicado
    assert data["creadas"] == 1
    assert data["actualizadas"] == 0

    fila = client.get(URL, headers=api_headers).get_json()["gestiones"][0]
    assert fila["descripcion"] == "segunda (gana)"  # última ocurrencia gana
    assert fila["coes_afectados"] == ["22222222222222"]


def test_post_gestiones_tipo_invalido_422(client, api_headers):
    g = _gestion(tipo="alta_pepe")
    resp = _post_batch(client, api_headers, [g])
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "validacion_fallida"


@pytest.mark.parametrize(
    "tipo,identificador",
    [
        ("cuenta_venta_grano", "22"),       # #142 pre-carga, bloqueante
        ("carga_inconsistente", "33023150836200"),  # #143 post-carga, no bloqueante
    ],
)
def test_post_gestiones_acepta_tipos_nuevos(client, api_headers, tipo, identificador):
    g = _gestion(tipo=tipo, identificador=identificador, descripcion=f"gestion {tipo}")
    resp = _post_batch(client, api_headers, [g])
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["creadas"] == 1

    fila = client.get(URL, headers=api_headers).get_json()["gestiones"][0]
    assert fila["tipo"] == tipo
    assert fila["estado"] == "pendiente"


# ---------------------------------------------------------------------------
# GET listado
# ---------------------------------------------------------------------------


def test_get_gestiones_filtra_por_estado_y_empresa(client, api_headers):
    g_a = _gestion(cuit_empresa="30711165378", identificador="20111111112")
    g_b = _gestion(cuit_empresa="30999999998", identificador="20222222223")
    _post_batch(client, api_headers, [g_a, g_b])

    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g_a["gestion_id"])

    # Filtra por estado
    realizadas = client.get(f"{URL}?estado=realizada", headers=api_headers).get_json()
    assert realizadas["total"] == 1
    assert realizadas["gestiones"][0]["gestion_id"] == g_a["gestion_id"]

    # Filtra por empresa
    empresa_b = client.get(f"{URL}?cuit_empresa=30999999998", headers=api_headers).get_json()
    assert empresa_b["total"] == 1
    assert empresa_b["gestiones"][0]["cuit_empresa"] == "30999999998"


# ---------------------------------------------------------------------------
# POST verificacion
# ---------------------------------------------------------------------------


def test_post_verificacion_realizada_a_verificada(client, api_headers):
    g = _gestion()
    _post_batch(client, api_headers, [g])
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"])

    resp = client.post(
        f"{URL}/{g['gestion_id']}/verificacion",
        json={"resultado": "verificada", "detalle": "Encontrado en SUSCRIP.DBF"},
        headers=api_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"gestion_id": g["gestion_id"], "estado": "verificada"}

    fila = client.get(URL, headers=api_headers).get_json()["gestiones"][0]
    assert fila["estado"] == "verificada"
    assert fila["verificada_en"] is not None
    assert fila["verificacion_detalle"] == "Encontrado en SUSCRIP.DBF"


def test_post_verificacion_realizada_a_fallida(client, api_headers):
    g = _gestion()
    _post_batch(client, api_headers, [g])
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"])

    resp = client.post(
        f"{URL}/{g['gestion_id']}/verificacion",
        json={"resultado": "verificacion_fallida", "detalle": "No aparece"},
        headers=api_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "verificacion_fallida"


def test_post_verificacion_desde_pendiente_409(client, api_headers):
    g = _gestion()
    _post_batch(client, api_headers, [g])  # queda pendiente

    resp = client.post(
        f"{URL}/{g['gestion_id']}/verificacion",
        json={"resultado": "verificada"},
        headers=api_headers,
    )
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error"] == "transicion_invalida"
    assert data["detalle"]["estado_actual"] == "pendiente"


def test_verificacion_gestion_inexistente_404(client, api_headers):
    resp = client.post(
        f"{URL}/g_noexiste00000000/verificacion",
        json={"resultado": "verificada"},
        headers=api_headers,
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "gestion_no_encontrada"


def test_verificacion_reconfirm_verificada_idempotente_200(client, api_headers):
    """Re-confirm sobre una gestión ya verificada → 200 no-op, no 409.

    Cubre el re-confirm pass del RPA tras lost-ack (review cross-repo PR #131).
    """
    g = _gestion()
    _post_batch(client, api_headers, [g])
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"])
    # Primer confirm: realizada → verificada
    r1 = client.post(f"{URL}/{g['gestion_id']}/verificacion", json={"resultado": "verificada"}, headers=api_headers)
    assert r1.status_code == 200
    # Re-confirm (ACK perdido): ya está verificada → no-op 200
    r2 = client.post(f"{URL}/{g['gestion_id']}/verificacion", json={"resultado": "verificada"}, headers=api_headers)
    assert r2.status_code == 200
    assert r2.get_json() == {"gestion_id": g["gestion_id"], "estado": "verificada"}


def test_verificacion_reconfirm_fallida_idempotente_200(client, api_headers):
    g = _gestion()
    _post_batch(client, api_headers, [g])
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"])
    client.post(f"{URL}/{g['gestion_id']}/verificacion", json={"resultado": "verificacion_fallida"}, headers=api_headers)
    # Re-confirm fallida: ya está fallida → no-op 200
    r = client.post(f"{URL}/{g['gestion_id']}/verificacion", json={"resultado": "verificacion_fallida"}, headers=api_headers)
    assert r.status_code == 200
    assert r.get_json()["estado"] == "verificacion_fallida"


def test_verificacion_verificada_a_fallida_sigue_409(client, api_headers):
    """El fix idempotente NO debe abrir verificada→fallida (verificada es terminal, §4)."""
    g = _gestion()
    _post_batch(client, api_headers, [g])
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"])
    client.post(f"{URL}/{g['gestion_id']}/verificacion", json={"resultado": "verificada"}, headers=api_headers)
    # Intentar moverla a fallida → 409 (terminal)
    r = client.post(f"{URL}/{g['gestion_id']}/verificacion", json={"resultado": "verificacion_fallida"}, headers=api_headers)
    assert r.status_code == 409
    assert r.get_json()["detalle"]["estado_actual"] == "verificada"


# ---------------------------------------------------------------------------
# Re-marca desde fallida (SPEC §4)
# ---------------------------------------------------------------------------


def test_marcar_realizada_desde_fallida_ok(client, api_headers):
    g = _gestion()
    _post_batch(client, api_headers, [g])
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"])
    gestiones_service.confirmar_verificacion(g["gestion_id"], resultado="verificacion_fallida")

    # El personal corrige y re-marca
    res = gestiones_service.marcar_realizada(g["gestion_id"], usuario="ana.estudio")
    assert res["estado"] == "realizada"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_endpoints_sin_apikey_401(client):
    g = _gestion()
    assert client.post(URL, json={"gestiones": [g]}).status_code == 401
    assert client.get(URL).status_code == 401
    assert client.post(f"{URL}/{g['gestion_id']}/verificacion", json={"resultado": "verificada"}).status_code == 401


# ---------------------------------------------------------------------------
# UI personal: marcar realizada (JWT) — SPEC §8.6
# ---------------------------------------------------------------------------


def test_marcar_realizada_endpoint_jwt(client, api_headers, auth_headers):
    """El personal marca hecha vía JWT; set realizada_por desde la sesión."""
    g = _gestion()
    _post_batch(client, api_headers, [g])  # creada vía API-key (RPA)

    resp = client.post(f"{URL}/{g['gestion_id']}/realizada", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["estado"] == "realizada"
    assert data["realizada_por"] == "testuser"  # username del fixture auth_headers
    assert data["realizada_en"] is not None


def test_marcar_realizada_desde_verificada_409(client, api_headers, auth_headers):
    g = _gestion()
    _post_batch(client, api_headers, [g])
    from app.services import gestiones_service
    gestiones_service.marcar_realizada(g["gestion_id"])
    gestiones_service.confirmar_verificacion(g["gestion_id"], resultado="verificada")

    resp = client.post(f"{URL}/{g['gestion_id']}/realizada", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.get_json()["detalle"]["estado_actual"] == "verificada"


def test_get_gestiones_acepta_jwt(client, api_headers, auth_headers):
    """La UI lista con JWT (sin API-key)."""
    g = _gestion()
    _post_batch(client, api_headers, [g])
    resp = client.get(URL, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 1


# ---------------------------------------------------------------------------
# Contrato gestion_id (mismo fixture compartido que RPA)
# ---------------------------------------------------------------------------


def test_gestion_id_contract():
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "gestion_id_contract.json"
    casos = json.loads(fixture.read_text(encoding="utf-8"))
    assert casos, "fixture vacío"
    for caso in casos:
        got = calcular_gestion_id(**caso["input"])
        assert got == caso["gestion_id_esperado"], (
            f"gestion_id divergente para {caso['input']}: {got} != {caso['gestion_id_esperado']}"
        )
