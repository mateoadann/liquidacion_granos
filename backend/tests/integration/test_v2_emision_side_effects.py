"""Tests de side-effects de emisión en GET /v2/liquidaciones.

Ver docs/spec_fix_emision_v2.md. El GET debe persistir
hash_payload_emitido + descargado_en + transicionar pendiente→descargado
de forma idempotente. Re-llamadas no rotan hashes ni timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import CoeEstado, LpgDocument, Taxpayer
from app.services.coe_estado_service import calcular_hash
from app.time_utils import now_cordoba_naive

API_KEY = "test-integration-key"
URL = "/api/v2/liquidaciones"


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


def _create_taxpayer(
    *,
    cuit: str = "20304050607",
    cuit_representado: str = "30711165378",
    scheduler_activo: bool = True,
) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = "Acopio SA"
    item.cuit_representado = cuit_representado
    item.clave_fiscal_encrypted = "test"
    item.activo = True
    item.scheduler_activo = scheduler_activo
    db.session.add(item)
    db.session.commit()
    return item


def _create_doc(*, taxpayer_id: int, coe: str) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.tipo_documento = "LPG"
    doc.datos_limpios = dict(SAMPLE_DATOS_LIMPIOS)
    db.session.add(doc)
    db.session.commit()
    return doc


def _create_coe_estado(
    *,
    coe: str,
    cuit_empresa: str = "30711165378",
    estado: str = "pendiente",
    lpg_document_id: int | None = None,
    hash_payload_emitido: str | None = None,
    descargado_en: datetime | None = None,
) -> CoeEstado:
    entry = CoeEstado(
        coe=coe,
        cuit_empresa=cuit_empresa,
        estado=estado,
        lpg_document_id=lpg_document_id,
        hash_payload_emitido=hash_payload_emitido,
        descargado_en=descargado_en,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


# ─── primera emisión: setea hash + descargado_en + estado ──────────────


def test_primera_emision_setea_hash_y_descargado_en(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        doc = _create_doc(taxpayer_id=t.id, coe="33010000000001")
        entry = _create_coe_estado(
            coe="33010000000001",
            lpg_document_id=doc.id,
            estado="pendiente",
        )
        coe_id = entry.id

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200

    with app.app_context():
        refreshed = db.session.get(CoeEstado, coe_id)
        assert refreshed.hash_payload_emitido is not None
        assert refreshed.hash_payload_emitido.startswith("sha256:")
        assert refreshed.descargado_en is not None
        assert refreshed.estado == "descargado"


def test_hash_emitido_matchea_payload_del_response(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        doc = _create_doc(taxpayer_id=t.id, coe="33010000000002")
        _create_coe_estado(
            coe="33010000000002",
            lpg_document_id=doc.id,
            estado="pendiente",
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["liquidaciones"]) == 1
    liq = body["liquidaciones"][0]
    hash_esperado = calcular_hash(liq)

    with app.app_context():
        refreshed = CoeEstado.query.filter_by(coe="33010000000002").first()
        assert refreshed.hash_payload_emitido == hash_esperado


# ─── idempotencia: re-llamar no pisa valores ───────────────────────────


def test_segunda_llamada_no_rota_hash_ni_descargado_en(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        doc = _create_doc(taxpayer_id=t.id, coe="33010000000010")
        _create_coe_estado(
            coe="33010000000010",
            lpg_document_id=doc.id,
            estado="pendiente",
        )

    # N=1
    resp1 = client.get(URL, headers=api_headers)
    assert resp1.status_code == 200

    with app.app_context():
        first = CoeEstado.query.filter_by(coe="33010000000010").first()
        hash_emitido_1 = first.hash_payload_emitido
        descargado_en_1 = first.descargado_en
        estado_1 = first.estado

    # N=2
    resp2 = client.get(URL, headers=api_headers)
    assert resp2.status_code == 200

    with app.app_context():
        second = CoeEstado.query.filter_by(coe="33010000000010").first()
        assert second.hash_payload_emitido == hash_emitido_1
        assert second.descargado_en == descargado_en_1
        assert second.estado == estado_1 == "descargado"


def test_coe_ya_cargado_se_devuelve_pero_no_se_toca(client, app, api_headers):
    hash_previo = "sha256:" + "a" * 64
    descargado_previo = now_cordoba_naive() - timedelta(days=2)

    with app.app_context():
        t = _create_taxpayer()
        doc = _create_doc(taxpayer_id=t.id, coe="33010000000020")
        _create_coe_estado(
            coe="33010000000020",
            lpg_document_id=doc.id,
            estado="cargado",
            hash_payload_emitido=hash_previo,
            descargado_en=descargado_previo,
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    body = resp.get_json()
    coes_en_body = [liq["coe"] for liq in body["liquidaciones"]]
    assert "33010000000020" in coes_en_body

    with app.app_context():
        refreshed = CoeEstado.query.filter_by(coe="33010000000020").first()
        assert refreshed.estado == "cargado"  # no regresó
        assert refreshed.hash_payload_emitido == hash_previo  # no se pisó
        assert refreshed.descargado_en == descargado_previo  # no se rotó


# ─── rollback: si los side-effects fallan, no se commitea nada ──────────


def test_rollback_si_side_effects_lanzan_excepcion(client, app, api_headers):
    with app.app_context():
        t = _create_taxpayer()
        doc = _create_doc(taxpayer_id=t.id, coe="33010000000030")
        entry = _create_coe_estado(
            coe="33010000000030",
            lpg_document_id=doc.id,
            estado="pendiente",
        )
        coe_id = entry.id

    with patch(
        "app.api.integration._aplicar_side_effects_emision",
        side_effect=RuntimeError("falla simulada en side-effects"),
    ):
        # Flask con TESTING=True propaga la excepción al test
        with pytest.raises(RuntimeError, match="falla simulada"):
            client.get(URL, headers=api_headers)

    with app.app_context():
        refreshed = db.session.get(CoeEstado, coe_id)
        # El COE NO debe haber sido modificado — rollback completo
        assert refreshed.hash_payload_emitido is None
        assert refreshed.descargado_en is None
        assert refreshed.estado == "pendiente"
