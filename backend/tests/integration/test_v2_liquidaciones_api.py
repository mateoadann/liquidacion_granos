from __future__ import annotations

import pytest

from app.extensions import db
from app.models import CoeEstado, LpgDocument, Taxpayer

API_KEY = "test-integration-key"


@pytest.fixture()
def api_headers():
    return {"X-API-Key": API_KEY}


SAMPLE_DATOS_LIMPIOS = {
    "codTipoOperacion": 1,
    "fechaLiquidacion": "2026-03-15",
    "cuitComprador": 30502874353,
    "codGrano": 15,
    "precioOperacion": 205.6,
    "totalPesoNeto": 38193.0,
    "subTotal": 7852593.91,
    "importeIva": 824522.36,
    "operacionConIva": 8677116.27,
}


def _build_datos(fecha: str = "2026-03-15", **overrides) -> dict:
    datos = dict(SAMPLE_DATOS_LIMPIOS)
    datos["fechaLiquidacion"] = fecha
    datos.update(overrides)
    return datos


def _create_taxpayer(
    *,
    cuit: str = "20304050607",
    cuit_representado: str = "30711165378",
    activo: bool = True,
    scheduler_activo: bool = True,
    empresa: str = "Acopio SA",
) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit_representado
    item.clave_fiscal_encrypted = "test"
    item.activo = activo
    item.scheduler_activo = scheduler_activo
    db.session.add(item)
    db.session.commit()
    return item


def _create_doc(
    *,
    taxpayer_id: int,
    coe: str,
    datos_limpios: dict | None = None,
    tipo_documento: str = "LPG",
) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.tipo_documento = tipo_documento
    doc.datos_limpios = datos_limpios or _build_datos()
    db.session.add(doc)
    db.session.commit()
    return doc


def _create_coe_estado(
    *,
    coe: str,
    cuit_empresa: str = "30711165378",
    estado: str = "pendiente",
    lpg_document_id: int | None = None,
) -> CoeEstado:
    entry = CoeEstado(
        coe=coe,
        cuit_empresa=cuit_empresa,
        estado=estado,
        lpg_document_id=lpg_document_id,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


URL = "/api/v2/liquidaciones"


# -----------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------


def test_get_sin_api_key_devuelve_401(client):
    resp = client.get(URL)
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "api_key_invalida"


def test_get_api_key_invalida_devuelve_401(client):
    resp = client.get(URL, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


# -----------------------------------------------------------------------
# Sin filtros: todas las liquidaciones
# -----------------------------------------------------------------------


def test_get_sin_filtros_devuelve_todas_las_liquidaciones(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        _create_doc(taxpayer_id=t.id, coe="33010000000001")
        _create_doc(taxpayer_id=t.id, coe="33010000000002", datos_limpios=_build_datos(fecha="2026-04-01"))

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema_version"] == "v7.1"
    assert len(data["liquidaciones"]) == 2
    coes = {liq["coe"] for liq in data["liquidaciones"]}
    assert coes == {"33010000000001", "33010000000002"}


# -----------------------------------------------------------------------
# Filtros por fecha
# -----------------------------------------------------------------------


def test_get_filtra_por_desde_fecha_emision(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        _create_doc(taxpayer_id=t.id, coe="33010000000010", datos_limpios=_build_datos(fecha="2026-01-15"))
        _create_doc(taxpayer_id=t.id, coe="33010000000011", datos_limpios=_build_datos(fecha="2026-03-15"))
        _create_doc(taxpayer_id=t.id, coe="33010000000012", datos_limpios=_build_datos(fecha="2026-05-15"))

    resp = client.get(URL, query_string={"desde_fecha_emision": "2026-03-01"}, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    coes = {liq["coe"] for liq in data["liquidaciones"]}
    assert coes == {"33010000000011", "33010000000012"}


def test_get_filtra_por_hasta_fecha_emision(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        _create_doc(taxpayer_id=t.id, coe="33010000000020", datos_limpios=_build_datos(fecha="2026-01-15"))
        _create_doc(taxpayer_id=t.id, coe="33010000000021", datos_limpios=_build_datos(fecha="2026-03-15"))
        _create_doc(taxpayer_id=t.id, coe="33010000000022", datos_limpios=_build_datos(fecha="2026-05-15"))

    resp = client.get(URL, query_string={"hasta_fecha_emision": "2026-03-31"}, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    coes = {liq["coe"] for liq in data["liquidaciones"]}
    assert coes == {"33010000000020", "33010000000021"}


def test_get_filtra_por_rango_completo(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        _create_doc(taxpayer_id=t.id, coe="33010000000030", datos_limpios=_build_datos(fecha="2026-01-15"))
        _create_doc(taxpayer_id=t.id, coe="33010000000031", datos_limpios=_build_datos(fecha="2026-03-15"))
        _create_doc(taxpayer_id=t.id, coe="33010000000032", datos_limpios=_build_datos(fecha="2026-05-15"))

    resp = client.get(
        URL,
        query_string={"desde_fecha_emision": "2026-02-01", "hasta_fecha_emision": "2026-04-30"},
        headers=api_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    coes = {liq["coe"] for liq in data["liquidaciones"]}
    assert coes == {"33010000000031"}


# -----------------------------------------------------------------------
# Filtro por cuit_empresa (repetible)
# -----------------------------------------------------------------------


def test_get_filtra_por_cuit_empresa_repetible(client, app, api_headers):
    with app.app_context():
        t1 = _create_taxpayer(cuit="20111111111", cuit_representado="30111111111", empresa="A")
        t2 = _create_taxpayer(cuit="20222222222", cuit_representado="30222222222", empresa="B")
        t3 = _create_taxpayer(cuit="20333333333", cuit_representado="30333333333", empresa="C")
        _create_doc(taxpayer_id=t1.id, coe="33010000000100")
        _create_doc(taxpayer_id=t2.id, coe="33010000000101")
        _create_doc(taxpayer_id=t3.id, coe="33010000000102")

    resp = client.get(
        URL + "?cuit_empresa=30111111111&cuit_empresa=30333333333",
        headers=api_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    coes = {liq["coe"] for liq in data["liquidaciones"]}
    assert coes == {"33010000000100", "33010000000102"}


# -----------------------------------------------------------------------
# Side-effects idempotentes acotados (ver docs/spec_fix_emision_v2.md)
#
# El endpoint persiste hash_payload_emitido + descargado_en y transiciona
# pendiente→descargado por cada COE emitido. Re-llamadas son no-op.
# Los tests detallados de idempotencia y rollback viven en
# tests/integration/test_v2_emision_side_effects.py.
# -----------------------------------------------------------------------


def test_get_transiciona_pendiente_a_descargado_y_preserva_otros(
    client, app, api_headers
):
    with app.app_context():
        t = _create_taxpayer()
        doc1 = _create_doc(taxpayer_id=t.id, coe="33010000000200")
        doc2 = _create_doc(taxpayer_id=t.id, coe="33010000000201")
        _create_coe_estado(
            coe="33010000000200", estado="pendiente", lpg_document_id=doc1.id
        )
        _create_coe_estado(
            coe="33010000000201", estado="descargado", lpg_document_id=doc2.id
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200

    with app.app_context():
        e1 = CoeEstado.query.filter_by(coe="33010000000200").first()
        e2 = CoeEstado.query.filter_by(coe="33010000000201").first()
        # pendiente → descargado, con hash + descargado_en seteados
        assert e1.estado == "descargado"
        assert e1.hash_payload_emitido is not None
        assert e1.hash_payload_emitido.startswith("sha256:")
        assert e1.descargado_en is not None
        # descargado preserva su estado, pero recibe hash + descargado_en
        # si estaban en null (primera emisión)
        assert e2.estado == "descargado"


# -----------------------------------------------------------------------
# Schema
# -----------------------------------------------------------------------


def test_get_devuelve_schema_v7_1_valido(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        _create_doc(taxpayer_id=t.id, coe="33010000000300")

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["schema_version"] == "v7.1"
    assert isinstance(data["liquidaciones"], list)

    meta = data["meta"]
    assert meta["fuente"] == "api_v2_liquidaciones"
    assert "generado_en" in meta
    assert "filtros_aplicados" in meta
    assert meta["total_liquidaciones"] == len(data["liquidaciones"])
    # Generador v2 distinto del v1
    assert meta["generador"].startswith("liquidacion-granos@2")


def test_get_meta_incluye_filtros_aplicados(client, app, api_headers):
    with app.app_context():
        _create_taxpayer()

    resp = client.get(
        URL + "?desde_fecha_emision=2026-01-01&hasta_fecha_emision=2026-12-31&cuit_empresa=30711165378",
        headers=api_headers,
    )
    assert resp.status_code == 200
    filtros = resp.get_json()["meta"]["filtros_aplicados"]
    assert filtros["desde_fecha_emision"] == "2026-01-01"
    assert filtros["hasta_fecha_emision"] == "2026-12-31"
    assert filtros["cuit_empresa"] == ["30711165378"]


# -----------------------------------------------------------------------
# Validación 422
# -----------------------------------------------------------------------


def test_get_fecha_mal_formada_devuelve_422(client, app, api_headers):
    with app.app_context():
        _create_taxpayer()

    resp = client.get(URL + "?desde_fecha_emision=15/03/2026", headers=api_headers)
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["error"] == "validacion_fallida"
    assert "desde_fecha_emision" in str(data.get("detalle", {}))


def test_get_hasta_fecha_mal_formada_devuelve_422(client, app, api_headers):
    with app.app_context():
        _create_taxpayer()

    resp = client.get(URL + "?hasta_fecha_emision=not-a-date", headers=api_headers)
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["error"] == "validacion_fallida"


# -----------------------------------------------------------------------
# Filtros por taxpayer flags
# -----------------------------------------------------------------------


def test_get_ignora_taxpayers_con_scheduler_activo_false(client, app, api_headers):
    with app.app_context():
        t_on = _create_taxpayer(cuit="20111111111", cuit_representado="30111111111", scheduler_activo=True)
        t_off = _create_taxpayer(cuit="20222222222", cuit_representado="30222222222", scheduler_activo=False)
        _create_doc(taxpayer_id=t_on.id, coe="33010000000400")
        _create_doc(taxpayer_id=t_off.id, coe="33010000000401")

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    coes = {liq["coe"] for liq in resp.get_json()["liquidaciones"]}
    assert coes == {"33010000000400"}


def test_get_ignora_taxpayers_con_activo_false(client, app, api_headers):
    with app.app_context():
        t_on = _create_taxpayer(cuit="20111111111", cuit_representado="30111111111", activo=True)
        t_off = _create_taxpayer(cuit="20222222222", cuit_representado="30222222222", activo=False)
        _create_doc(taxpayer_id=t_on.id, coe="33010000000500")
        _create_doc(taxpayer_id=t_off.id, coe="33010000000501")

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    coes = {liq["coe"] for liq in resp.get_json()["liquidaciones"]}
    assert coes == {"33010000000500"}


# -----------------------------------------------------------------------
# Estado universo completo (no filtra por CoeEstado.estado)
# -----------------------------------------------------------------------


def test_get_devuelve_universo_completo_sin_filtrar_por_estado(client, app, api_headers):
    """SPEC §18: GET /v2/liquidaciones devuelve el universo, no filtra cargados."""
    with app.app_context():
        t = _create_taxpayer()
        doc1 = _create_doc(taxpayer_id=t.id, coe="33010000000600")
        doc2 = _create_doc(taxpayer_id=t.id, coe="33010000000601")
        doc3 = _create_doc(taxpayer_id=t.id, coe="33010000000602")
        _create_coe_estado(coe="33010000000600", estado="pendiente", lpg_document_id=doc1.id)
        _create_coe_estado(coe="33010000000601", estado="descargado", lpg_document_id=doc2.id)
        _create_coe_estado(coe="33010000000602", estado="cargado", lpg_document_id=doc3.id)

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    coes = {liq["coe"] for liq in resp.get_json()["liquidaciones"]}
    assert coes == {"33010000000600", "33010000000601", "33010000000602"}
