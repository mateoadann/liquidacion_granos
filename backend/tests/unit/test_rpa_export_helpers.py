from __future__ import annotations

import pytest

from app.api.clients import (
    _build_rpa_row,
    _format_fecha_emision,
    _map_codigo_comprobante,
)
from app.models import LpgDocument


def _make_doc(
    tipo_documento: str = "LPG",
    coe: str = "330230787118",
    datos_limpios: dict | None = None,
    raw_data: dict | None = None,
) -> LpgDocument:
    """Build an LpgDocument instance without persisting to the database."""
    doc = LpgDocument()
    doc.tipo_documento = tipo_documento
    doc.coe = coe
    doc.datos_limpios = datos_limpios
    doc.raw_data = raw_data
    return doc


# ─── _map_codigo_comprobante ─────────────────────────────────────────


class TestMapCodigoComprobante:
    def test_ajuste_returns_nl(self):
        doc = _make_doc(tipo_documento="AJUSTE")
        assert _map_codigo_comprobante(doc) == "NL"

    def test_ajuste_ignores_cod_tipo_operacion(self):
        doc = _make_doc(
            tipo_documento="AJUSTE",
            datos_limpios={"codTipoOperacion": 2},
        )
        assert _map_codigo_comprobante(doc) == "NL"

    def test_lpg_cod_tipo_operacion_1_int(self):
        doc = _make_doc(datos_limpios={"codTipoOperacion": 1})
        assert _map_codigo_comprobante(doc) == "F1"

    def test_lpg_cod_tipo_operacion_1_str(self):
        doc = _make_doc(datos_limpios={"codTipoOperacion": "1"})
        assert _map_codigo_comprobante(doc) == "F1"

    def test_lpg_cod_tipo_operacion_2_int(self):
        doc = _make_doc(datos_limpios={"codTipoOperacion": 2})
        assert _map_codigo_comprobante(doc) == "F2"

    def test_lpg_cod_tipo_operacion_2_str(self):
        doc = _make_doc(datos_limpios={"codTipoOperacion": "2"})
        assert _map_codigo_comprobante(doc) == "F2"

    def test_lpg_no_cod_tipo_operacion_defaults_to_f1(self):
        doc = _make_doc(datos_limpios={})
        assert _map_codigo_comprobante(doc) == "F1"

    def test_lpg_no_data_at_all_defaults_to_f1(self):
        doc = _make_doc()
        assert _map_codigo_comprobante(doc) == "F1"


# ─── _format_fecha_emision ───────────────────────────────────────────


class TestFormatFechaEmision:
    def test_standard_date(self):
        assert _format_fecha_emision("2026-02-12") == "12022026"

    def test_first_of_month(self):
        assert _format_fecha_emision("2026-12-01") == "01122026"

    def test_none_returns_empty(self):
        assert _format_fecha_emision(None) == ""

    def test_empty_string_returns_empty(self):
        assert _format_fecha_emision("") == ""

    def test_invalid_format_returns_empty(self):
        assert _format_fecha_emision("12/02/2026") == ""


# ─── _build_rpa_row ─────────────────────────────────────────────────


class TestBuildRpaRow:
    def test_normal_lpg_document(self):
        doc = _make_doc(
            coe="330230787118",
            datos_limpios={
                "codTipoOperacion": 1,
                "fechaLiquidacion": "2026-02-15",
            },
        )
        row = _build_rpa_row(doc, empresa="Acopio SA", mes="2", anio="2026")

        assert row["empresa"] == "Acopio SA"
        assert row["mes"] == "2"
        assert row["anio"] == "2026"
        assert row["codigo_comprobante"] == "F1"
        assert row["tipo_pto_vta"] == "3302"
        assert row["nro_comprobante"] == "30787118"
        assert row["fecha_emision"] == "15022026"

    def test_coe_split_first_four_and_rest(self):
        doc = _make_doc(
            coe="330230787118",
            datos_limpios={"fechaLiquidacion": "2026-03-01"},
        )
        row = _build_rpa_row(doc, empresa="Test", mes="3", anio="2026")
        assert row["tipo_pto_vta"] == "3302"
        assert row["nro_comprobante"] == "30787118"

    def test_short_coe_defensive(self):
        doc = _make_doc(
            coe="AB",
            datos_limpios={"fechaLiquidacion": "2026-01-10"},
        )
        row = _build_rpa_row(doc, empresa="Test", mes="1", anio="2026")
        assert row["tipo_pto_vta"] == "AB"
        assert row["nro_comprobante"] == ""

    def test_empty_coe(self):
        doc = _make_doc(coe="", datos_limpios={"fechaLiquidacion": "2026-01-10"})
        row = _build_rpa_row(doc, empresa="Test", mes="1", anio="2026")
        assert row["tipo_pto_vta"] == ""
        assert row["nro_comprobante"] == ""

    def test_none_coe(self):
        doc = _make_doc(coe=None, datos_limpios={"fechaLiquidacion": "2026-01-10"})
        doc.coe = None
        row = _build_rpa_row(doc, empresa="Test", mes="1", anio="2026")
        assert row["tipo_pto_vta"] == ""
        assert row["nro_comprobante"] == ""
