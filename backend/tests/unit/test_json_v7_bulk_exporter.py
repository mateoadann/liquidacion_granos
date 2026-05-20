from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.coe_estado import CoeEstado
from app.services.json_v7_exporter import build_json_v7_bulk


SAMPLE_DATOS = {
    "codTipoOperacion": 2,
    "fechaLiquidacion": "2025-12-15",
    "cuitComprador": 30500120882,
    "cuitVendedor": 30711165378,
    "codGrano": 15,
    "precioOperacion": 265.187,
    "totalPesoNeto": 29086,
    "subTotal": 7713215.85,
    "importeIva": 809887.66,
    "operacionConIva": 8523103.51,
    "retenciones": [],
    "deducciones": [],
}


def _make_taxpayer(cuit_representado: str = "30500120882") -> SimpleNamespace:
    return SimpleNamespace(cuit_representado=cuit_representado)


def _make_doc(
    coe: str = "330230384112",
    datos: dict | None = None,
    tipo_documento: str = "LPG",
    taxpayer: SimpleNamespace | None = None,
    doc_id: int | None = 1,
    nro_orden: int | None = None,
    pto_emision: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=doc_id,
        coe=coe,
        tipo_documento=tipo_documento,
        datos_limpios=datos if datos is not None else SAMPLE_DATOS,
        pto_emision=pto_emision,
        nro_orden=nro_orden,
        taxpayer=taxpayer if taxpayer is not None else _make_taxpayer(),
    )


def _make_coe_estado(
    coe: str,
    cuit_empresa: str = "30500120882",
    estado: str = "pendiente",
    id_liquidacion: str | None = None,
) -> CoeEstado:
    entry = CoeEstado(
        coe=coe,
        cuit_empresa=cuit_empresa,
        estado=estado,
        id_liquidacion=id_liquidacion,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


# ─── schema básico ─────────────────────────────────────────────────────


def test_build_bulk_returns_schema_v7_1(app):
    doc = _make_doc()
    body, _ = build_json_v7_bulk([doc], filtros={})
    assert body["schema_version"] == "v7.1"
    assert "meta" in body
    assert "liquidaciones" in body
    assert isinstance(body["liquidaciones"], list)
    assert len(body["liquidaciones"]) == 1


def test_build_bulk_meta_includes_fuente_and_filtros(app):
    doc = _make_doc()
    filtros = {"cuit_empresa": "30500120882", "desde": "2025-01-01", "hasta": "2025-12-31"}
    body, _ = build_json_v7_bulk([doc], filtros=filtros)
    meta = body["meta"]
    assert meta["fuente"] == "api_v2_liquidaciones"
    assert meta["filtros_aplicados"] == filtros
    assert meta["generador"] == "liquidacion-granos@2.0.0"
    assert "generado_en" in meta


def test_build_bulk_meta_total_matches_liquidaciones_length(app):
    docs = [
        _make_doc(coe="110000000001", doc_id=1),
        _make_doc(coe="110000000002", doc_id=2),
        _make_doc(coe="110000000003", doc_id=3),
    ]
    body, _ = build_json_v7_bulk(docs, filtros={})
    assert body["meta"]["total_liquidaciones"] == 3
    assert len(body["liquidaciones"]) == 3
    assert body["meta"]["total_liquidaciones"] == len(body["liquidaciones"])


# ─── NO filtra cargado ─────────────────────────────────────────────────


def test_build_bulk_does_NOT_filter_cargado(app):
    coe = "110000000010"
    _make_coe_estado(coe=coe, estado="cargado", id_liquidacion="liq_already_loaded")

    doc = _make_doc(coe=coe)
    body, _ = build_json_v7_bulk([doc], filtros={})

    # CoeEstado.estado == 'cargado' DEBE estar incluido (v2 devuelve el universo completo)
    assert len(body["liquidaciones"]) == 1
    liq = body["liquidaciones"][0]
    assert liq["coe"] == coe
    assert liq["estado_origen"] == "cargado"
    assert liq["id_liquidacion"] == "liq_already_loaded"


# ─── NO persiste por sí mismo ──────────────────────────────────────────


def test_build_bulk_does_NOT_persist_state_changes(app):
    coe = "110000000020"
    entry = _make_coe_estado(coe=coe, estado="pendiente")

    estado_antes = entry.estado
    descargado_en_antes = entry.descargado_en
    hash_antes = entry.hash_payload_emitido

    doc = _make_doc(coe=coe)
    body, coes_a_persistir = build_json_v7_bulk([doc], filtros={})

    # Re-fetch — el constructor NO debe haber persistido nada
    refreshed = CoeEstado.query.filter_by(coe=coe).first()
    assert refreshed.estado == estado_antes == "pendiente"
    assert refreshed.descargado_en == descargado_en_antes
    assert refreshed.hash_payload_emitido == hash_antes

    # Pero SÍ debe haber devuelto el COE en coes_a_persistir con su hash
    assert len(coes_a_persistir) == 1
    coe_estado_id, hash_calc = coes_a_persistir[0]
    assert coe_estado_id == entry.id
    assert hash_calc.startswith("sha256:")


def test_build_bulk_does_NOT_call_marcar_descargado(app):
    coe = "110000000021"
    _make_coe_estado(coe=coe, estado="pendiente")

    doc = _make_doc(coe=coe)

    with patch(
        "app.services.coe_estado_service.marcar_descargado"
    ) as mock_marcar:
        build_json_v7_bulk([doc], filtros={})

    mock_marcar.assert_not_called()


# ─── skips de docs inválidos ───────────────────────────────────────────


def test_build_bulk_skips_docs_without_taxpayer(app, caplog):
    doc_ok = _make_doc(coe="110000000030", doc_id=30)
    doc_no_tp = _make_doc(coe="110000000031", doc_id=31, taxpayer=None)
    # SimpleNamespace con taxpayer=None — getattr devuelve None
    doc_no_tp.taxpayer = None

    with caplog.at_level("WARNING"):
        body, _ = build_json_v7_bulk([doc_ok, doc_no_tp], filtros={})

    assert len(body["liquidaciones"]) == 1
    assert body["liquidaciones"][0]["coe"] == "110000000030"
    assert any(
        "BULK_EXPORT_SKIP_NO_TAXPAYER" in r.message for r in caplog.records
    )


def test_build_bulk_skips_docs_with_invalid_fecha_liquidacion(app, caplog):
    datos_invalida = {**SAMPLE_DATOS, "fechaLiquidacion": "no-es-fecha"}
    datos_sin_fecha = {k: v for k, v in SAMPLE_DATOS.items() if k != "fechaLiquidacion"}

    doc_ok = _make_doc(coe="110000000040", doc_id=40)
    doc_invalida = _make_doc(
        coe="110000000041", doc_id=41, datos=datos_invalida
    )
    doc_sin_fecha = _make_doc(
        coe="110000000042", doc_id=42, datos=datos_sin_fecha
    )

    with caplog.at_level("WARNING"):
        body, _ = build_json_v7_bulk(
            [doc_ok, doc_invalida, doc_sin_fecha], filtros={}
        )

    assert len(body["liquidaciones"]) == 1
    assert body["liquidaciones"][0]["coe"] == "110000000040"
    skip_logs = [
        r for r in caplog.records if "BULK_EXPORT_SKIP_INVALID_FECHA" in r.message
    ]
    assert len(skip_logs) == 2


# ─── estado_origen / id_liquidacion ────────────────────────────────────


def test_build_bulk_uses_pendiente_default_estado_origen_when_no_coe_estado(app):
    # No CoeEstado in DB
    doc = _make_doc(coe="110000000050")
    body, coes_a_persistir = build_json_v7_bulk([doc], filtros={})

    assert len(body["liquidaciones"]) == 1
    liq = body["liquidaciones"][0]
    assert liq["estado_origen"] == "pendiente"
    # transform_single genera un uuid liq_*
    assert liq["id_liquidacion"].startswith("liq_")
    # Sin CoeEstado row no hay nada para persistir
    assert coes_a_persistir == []


def test_build_bulk_reads_estado_and_id_from_coe_estado_when_exists(app):
    coe = "110000000060"
    _make_coe_estado(
        coe=coe,
        estado="descargado",
        id_liquidacion="liq_existing_abc123",
    )

    doc = _make_doc(coe=coe)
    body, _ = build_json_v7_bulk([doc], filtros={})

    assert len(body["liquidaciones"]) == 1
    liq = body["liquidaciones"][0]
    assert liq["estado_origen"] == "descargado"
    assert liq["id_liquidacion"] == "liq_existing_abc123"
