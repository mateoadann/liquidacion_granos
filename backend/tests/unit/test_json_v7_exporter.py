from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.json_v7_exporter import (
    _format_cuit,
    _build_comprobante,
    _build_grano,
    _build_retenciones,
    _build_deducciones,
    transform_single,
    build_json_v7,
)


def _make_doc(
    tipo_documento: str = "LPG",
    coe: str = "330230384112",
    datos_limpios: dict | None = None,
    pto_emision: int | None = None,
    nro_orden: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        tipo_documento=tipo_documento,
        coe=coe,
        datos_limpios=datos_limpios,
        pto_emision=pto_emision,
        nro_orden=nro_orden,
    )


def _make_taxpayer(cuit_representado: str = "30711165378") -> SimpleNamespace:
    return SimpleNamespace(cuit_representado=cuit_representado)


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
    "retenciones": [
        {
            "codigoConcepto": "RG",
            "detalleAclaratorio": "Detalle de Ret.Gan.",
            "baseCalculo": 7632279.6,
            "alicuota": 5,
            "importeRetencion": 381613.98,
            "nroCertificadoRetencion": None,
            "descConcepto": "Retencion Ganancias",
        },
        {
            "codigoConcepto": "RI",
            "detalleAclaratorio": "Detalle de Ret.IVA",
            "baseCalculo": 7632279.6,
            "alicuota": 10.5,
            "importeRetencion": 419775.38,
            "nroCertificadoRetencion": None,
            "descConcepto": "Retencion IVA",
        },
    ],
    "deducciones": [
        {
            "codigoConcepto": "OD",
            "detalleAclaratorio": "Derecho de Registro Cordoba",
            "baseCalculo": 80936.16,
            "alicuotaIva": 10.5,
            "importeIva": 8498.3,
            "importeDeduccion": 89434.46,
            "descConcepto": "Otras Deducciones",
        },
    ],
}


# ─── _format_cuit ──────────────────────────────────────────────────────


class TestFormatCuit:
    def test_format_cuit_from_int(self):
        assert _format_cuit(30711165378) == "30711165378"

    def test_format_cuit_from_string(self):
        assert _format_cuit("30711165378") == "30711165378"

    def test_format_cuit_strips_hyphens(self):
        assert _format_cuit("30-71116537-8") == "30711165378"

    def test_format_cuit_zero_pads(self):
        assert _format_cuit(1234567890) == "01234567890"


# ─── _build_comprobante ────────────────────────────────────────────────


class TestBuildComprobante:
    def test_build_comprobante_f2(self):
        doc = _make_doc(datos_limpios={"codTipoOperacion": 2})
        result = _build_comprobante(doc, {"codTipoOperacion": 2})
        assert result["codigo"] == "F2"

    def test_build_comprobante_f1(self):
        doc = _make_doc(datos_limpios={"codTipoOperacion": 1})
        result = _build_comprobante(doc, {"codTipoOperacion": 1})
        assert result["codigo"] == "F1"

    def test_build_comprobante_ajuste(self):
        doc = _make_doc(tipo_documento="AJUSTE")
        result = _build_comprobante(doc, {"codTipoOperacion": 2})
        assert result["codigo"] == "NL"

    def test_build_comprobante_coe_split_nro(self):
        doc = _make_doc(coe="330230384112")
        result = _build_comprobante(doc, {})
        assert result["nro"] == 30384112

    def test_build_comprobante_tipo_pto_vta_fixed_f1(self):
        doc = _make_doc(coe="061730384112")
        result = _build_comprobante(doc, {"codTipoOperacion": 1})
        assert result["tipo_pto_vta"] == 3301  # fixed, NOT 617 from COE

    def test_build_comprobante_tipo_pto_vta_fixed_f2(self):
        doc = _make_doc(coe="061730384112")
        result = _build_comprobante(doc, {"codTipoOperacion": 2})
        assert result["tipo_pto_vta"] == 3302  # fixed, NOT 617 from COE

    def test_build_comprobante_nro_from_doc_field(self):
        doc = _make_doc(coe="330230384112", nro_orden=12345678)
        result = _build_comprobante(doc, {})
        assert result["nro"] == 12345678


# ─── _build_grano ──────────────────────────────────────────────────────


class TestBuildGrano:
    def test_build_grano_maps_fields(self):
        result = _build_grano(SAMPLE_DATOS)
        assert result["cod_grano"] == 15
        assert result["precio_unitario"] == 265.19
        assert result["cantidad_kg"] == 29086
        assert result["neto_total"] == 7713215.85
        assert result["iva_monto"] == 809887.66
        assert result["subtotal"] == 8523103.51

    def test_build_grano_cantidad_kg_is_int(self):
        datos = {**SAMPLE_DATOS, "totalPesoNeto": 38193.0}
        result = _build_grano(datos)
        assert result["cantidad_kg"] == 38193
        assert isinstance(result["cantidad_kg"], int)


# ─── _build_retenciones ────────────────────────────────────────────────


class TestBuildRetenciones:
    def test_build_retenciones_basic(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "retenciones": [
                {
                    "codigoConcepto": "RI",
                    "importeRetencion": 419775.38,
                    "alicuota": 10.5,
                },
            ],
        }
        result = _build_retenciones(datos)
        assert len(result) == 1
        assert result[0]["codigo_arca"] == "RI"
        assert result[0]["importe"] == 419775.38
        assert result[0]["alicuota"] == 10.5
        assert result[0]["cuit_proveedor"] == "30500120882"

    def test_build_retenciones_iibb_unification(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "retenciones": [
                {
                    "codigoConcepto": "IB",
                    "importeRetencion": 200000,
                    "alicuota": 4.0,
                },
                {
                    "codigoConcepto": "OG",
                    "importeRetencion": 127489.77,
                    "alicuota": 4.0,
                },
            ],
        }
        result = _build_retenciones(datos)
        ib_items = [r for r in result if r["codigo_arca"] == "IB"]
        assert len(ib_items) == 1
        assert ib_items[0]["importe"] == pytest.approx(327489.77)
        assert ib_items[0]["alicuota"] == pytest.approx(8.0)

    def test_build_retenciones_only_ib_no_og(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "retenciones": [
                {
                    "codigoConcepto": "IB",
                    "importeRetencion": 200000,
                    "alicuota": 4.0,
                },
            ],
        }
        result = _build_retenciones(datos)
        assert len(result) == 1
        assert result[0]["codigo_arca"] == "IB"
        assert result[0]["importe"] == 200000

    def test_build_retenciones_only_og_no_ib(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "retenciones": [
                {
                    "codigoConcepto": "OG",
                    "importeRetencion": 127489.77,
                    "alicuota": 4.0,
                },
            ],
        }
        result = _build_retenciones(datos)
        assert len(result) == 1
        assert result[0]["codigo_arca"] == "IB"
        assert result[0]["importe"] == 127489.77

    def test_build_retenciones_no_og_in_output(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "retenciones": [
                {"codigoConcepto": "IB", "importeRetencion": 100, "alicuota": 2.0},
                {"codigoConcepto": "OG", "importeRetencion": 50, "alicuota": 1.0},
                {"codigoConcepto": "RG", "importeRetencion": 300, "alicuota": 5.0},
            ],
        }
        result = _build_retenciones(datos)
        codigos = [r["codigo_arca"] for r in result]
        assert "OG" not in codigos

    def test_build_retenciones_filters_zero_importe(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "retenciones": [
                {"codigoConcepto": "RI", "importeRetencion": 0, "alicuota": 10.5},
                {"codigoConcepto": "RG", "importeRetencion": 500, "alicuota": 5.0},
            ],
        }
        result = _build_retenciones(datos)
        assert len(result) == 1
        assert result[0]["codigo_arca"] == "RG"


# ─── _build_deducciones ────────────────────────────────────────────────


class TestBuildDeducciones:
    def test_build_deducciones_con_iva(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "deducciones": [
                {
                    "codigoConcepto": "CO",
                    "detalleAclaratorio": "Comision",
                    "baseCalculo": 80000,
                    "alicuotaIva": 10.5,
                    "importeIva": 8400,
                    "importeDeduccion": 88400,
                    "descConcepto": "Comision Operativa",
                },
            ],
        }
        result = _build_deducciones(datos)
        assert len(result) == 1
        assert result[0]["codigo_arca"] == "CO"
        assert result[0]["detalle"] == "Comision"
        assert result[0]["base"] == 80000
        assert result[0]["importe"] == 88400
        assert result[0]["alicuota_iva"] == 10.5
        assert result[0]["importe_iva"] == 8400
        assert result[0]["cuit_proveedor"] == "30500120882"

    def test_build_deducciones_sin_iva(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "deducciones": [
                {
                    "codigoConcepto": "OD",
                    "detalleAclaratorio": "",
                    "baseCalculo": 5000,
                    "alicuotaIva": 0,
                    "importeIva": 0,
                    "importeDeduccion": 5000,
                    "descConcepto": "Otras Deducciones",
                },
            ],
        }
        result = _build_deducciones(datos)
        assert len(result) == 1
        assert result[0]["alicuota_iva"] == 0
        assert result[0]["importe_iva"] == 0
        # detalle falls back to descConcepto when detalleAclaratorio is empty
        assert result[0]["detalle"] == "Otras Deducciones"

    def test_build_deducciones_filters_zero_importe(self):
        datos = {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "deducciones": [
                {
                    "codigoConcepto": "OD",
                    "detalleAclaratorio": "Zero",
                    "baseCalculo": 0,
                    "alicuotaIva": 0,
                    "importeIva": 0,
                    "importeDeduccion": 0,
                    "descConcepto": "Nada",
                },
            ],
        }
        result = _build_deducciones(datos)
        assert len(result) == 0


# ─── transform_single ──────────────────────────────────────────────────


class TestTransformSingle:
    def test_transform_single_full(self):
        doc = _make_doc(coe="330230384112", datos_limpios=SAMPLE_DATOS)
        taxpayer = _make_taxpayer("30500120882")
        result = transform_single(doc, taxpayer, mes=12, anio=2025)

        assert result["cuit_empresa"] == "30500120882"
        assert result["cuit_comprador"] == "30500120882"
        assert result["mes"] == 12
        assert result["anio"] == 2025
        assert result["comprobante"]["codigo"] == "F2"
        assert result["grano"]["cod_grano"] == 15
        assert "cuit_proveedor" in result
        assert result["cuit_proveedor"] == "30500120882"
        assert len(result["retenciones"]) == 2
        assert len(result["deducciones"]) == 1

    def test_transform_single_minimal(self):
        datos = {
            "codTipoOperacion": 1,
            "fechaLiquidacion": "2025-01-01",
            "cuitComprador": 20111111111,
            "codGrano": 2,
            "precioOperacion": 100.0,
            "totalPesoNeto": 1000,
            "subTotal": 100000,
            "importeIva": 10500,
            "operacionConIva": 110500,
            "retenciones": [],
            "deducciones": [],
        }
        doc = _make_doc(coe="110000000001", datos_limpios=datos)
        taxpayer = _make_taxpayer("20222222222")
        result = transform_single(doc, taxpayer, mes=1, anio=2025)

        assert "cuit_proveedor" not in result
        assert "retenciones" not in result
        assert "deducciones" not in result

    def test_transform_single_cuits_are_strings(self):
        doc = _make_doc(coe="330230384112", datos_limpios=SAMPLE_DATOS)
        taxpayer = _make_taxpayer("30500120882")
        result = transform_single(doc, taxpayer, mes=12, anio=2025)

        assert isinstance(result["cuit_empresa"], str)
        assert len(result["cuit_empresa"]) == 11
        assert isinstance(result["cuit_comprador"], str)
        assert len(result["cuit_comprador"]) == 11
        assert isinstance(result["cuit_proveedor"], str)
        assert len(result["cuit_proveedor"]) == 11


# ─── build_json_v7 ─────────────────────────────────────────────────────


class TestBuildJsonV7:
    def test_build_json_v7_wrapper(self, app):
        doc = _make_doc(coe="330230384112", datos_limpios=SAMPLE_DATOS)
        taxpayer = _make_taxpayer("30500120882")
        result = build_json_v7([doc], taxpayer, mes=12, anio=2025)

        assert "liquidaciones" in result
        assert isinstance(result["liquidaciones"], list)
        assert len(result["liquidaciones"]) == 1

    def test_build_json_v7_no_og_in_any_output(self, app):
        datos_with_og = {
            **SAMPLE_DATOS,
            "retenciones": [
                {"codigoConcepto": "IB", "importeRetencion": 100, "alicuota": 2.0},
                {"codigoConcepto": "OG", "importeRetencion": 50, "alicuota": 1.0},
                {"codigoConcepto": "RG", "importeRetencion": 300, "alicuota": 5.0},
            ],
        }
        doc1 = _make_doc(coe="110000000001", datos_limpios=datos_with_og)
        doc2 = _make_doc(coe="110000000002", datos_limpios=datos_with_og)
        taxpayer = _make_taxpayer("30500120882")
        result = build_json_v7([doc1, doc2], taxpayer, mes=12, anio=2025)

        for liq in result["liquidaciones"]:
            if "retenciones" in liq:
                for ret in liq["retenciones"]:
                    assert ret["codigo_arca"] != "OG", "OG must not appear in output"
