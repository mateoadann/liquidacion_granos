from __future__ import annotations

from app.extensions import db
from app.models import WslpgParameter, LpgDocument, Taxpayer
from app.services.datos_limpios_builder import DatosLimpiosBuilder


def _seed_parameters():
    params = [
        ("tipoGrano", "15", "TRIGO PAN"),
        ("gradoReferencia", "G2", "Grado 2"),
        ("gradoEntregado", "G2", "Grado 2"),
        ("puerto", "14", "OTROS"),
        ("provincia", "3", "CORDOBA"),
        ("localidad", "3_1443", "BENGOLEA"),
        ("tipoDeduccion", "OD", "Otras Deducciones"),
        ("tipoDeduccion", "GA", "Comision o Gastos Administrativos"),
        ("tipoRetencion", "RG", "Retencion Ganancias"),
        ("tipoRetencion", "RI", "Retencion IVA"),
        ("tipoOperacion", "2", "Consignacion"),
    ]
    for tabla, codigo, desc in params:
        db.session.add(WslpgParameter(tabla=tabla, codigo=codigo, descripcion=desc))
    db.session.commit()


SAMPLE_RAW_DATA = {
    "data": {
        "autorizacion": {
            "codTipoOperacion": 2,
            "coe": 330230101658,
            "fechaLiquidacion": "2025-12-15",
            "totalPesoNeto": 29086,
            "precioOperacion": 265.187,
            "subTotal": 7713215.85,
            "importeIva": 809887.66,
            "operacionConIva": 8523103.51,
            "deducciones": {
                "deduccionReturn": [
                    {
                        "deduccion": {
                            "codigoConcepto": "OD",
                            "detalleAclaratorio": "Derecho de Registro Cordoba",
                            "baseCalculo": 80936.16,
                            "alicuotaIva": 10.5,
                        },
                        "importeIva": 8498.3,
                        "importeDeduccion": 89434.46,
                    }
                ]
            },
            "retenciones": {
                "retencionReturn": [
                    {
                        "retencion": {
                            "codigoConcepto": "RG",
                            "detalleAclaratorio": "Detalle de Ret.Gan.",
                            "nroCertificadoRetencion": None,
                            "importeCertificadoRetencion": None,
                            "fechaCertificadoRetencion": None,
                            "baseCalculo": 7632279.6,
                            "alicuota": 5,
                        },
                        "importeRetencion": 381613.98,
                    }
                ]
            },
            "totalRetencionAfip": 381613.98,
            "totalNetoAPagar": 8042896.33,
            "totalPercepcion": 0,
            "totalOtrasRetenciones": 0,
            "totalIvaRg4310_18": 419775.38,
            "totalDeduccion": 98593.2,
            "totalPagoSegunCondicion": 7623120.95,
        },
        "liquidacion": {
            "cuitComprador": 30500120882,
            "cuitVendedor": 30711165378,
            "precioRefTn": 278265,
            "codGradoRef": "G2",
            "codGrano": 15,
            "precioFleteTn": 0,
            "codPuerto": 14,
            "codGradoEnt": "G2",
            "factorEnt": 95.3,
            "contProteico": 9.1,
            "alicIvaOperacion": 10.5,
            "codLocalidadProcedencia": 1443,
            "codProvProcedencia": 3,
            "certificados": {
                "certificado": [
                    {
                        "nroCertificadoDeposito": 332021671471,
                        "pesoNeto": 29086,
                    }
                ]
            },
        },
    }
}


def test_build_datos_limpios(app):
    with app.app_context():
        _seed_parameters()
        builder = DatosLimpiosBuilder()
        result = builder.build(SAMPLE_RAW_DATA)

        assert result["codTipoOperacion"] == 2
        assert result["descTipoOperacion"] == "Consignacion"
        assert result["coe"] == 330230101658
        assert result["fechaLiquidacion"] == "2025-12-15"
        assert result["cuitComprador"] == 30500120882
        assert result["cuitVendedor"] == 30711165378
        assert result["descGrano"] == "TRIGO PAN"
        assert result["descGradoRef"] == "Grado 2"
        assert result["descPuerto"] == "OTROS"
        assert result["descGradoEnt"] == "Grado 2"
        assert result["descLocalidadProcedencia"] == "BENGOLEA"
        assert result["descProvProcedencia"] == "CORDOBA"
        assert len(result["deducciones"]) == 1
        assert result["deducciones"][0]["descConcepto"] == "Otras Deducciones"
        assert len(result["retenciones"]) == 1
        assert result["retenciones"][0]["descConcepto"] == "Retencion Ganancias"
        assert result["totalPagoSegunCondicion"] == 7623120.95


def test_build_with_missing_params_uses_fallback(app):
    """When no parametric data in DB, builder falls back to raw code as string."""
    with app.app_context():
        builder = DatosLimpiosBuilder()
        result = builder.build(SAMPLE_RAW_DATA)
        assert result["descGrano"] == "15"
        assert result["descPuerto"] == "14"


def test_build_with_no_data_key(app):
    """When raw_data has no 'data' wrapper, builder falls back to flat read."""
    with app.app_context():
        _seed_parameters()
        # Pass the inner structure directly (no "data" wrapper)
        raw = dict(SAMPLE_RAW_DATA["data"])
        builder = DatosLimpiosBuilder()
        result = builder.build(raw)
        assert result["descGrano"] == "TRIGO PAN"


def test_build_with_none(app):
    with app.app_context():
        builder = DatosLimpiosBuilder()
        result = builder.build(None)
        assert result == {}


def test_process_document(app):
    with app.app_context():
        _seed_parameters()

        taxpayer = Taxpayer()
        taxpayer.cuit = "20111111111"
        taxpayer.empresa = "Test SA"
        taxpayer.cuit_representado = "20111111111"
        taxpayer.clave_fiscal_encrypted = "x"
        db.session.add(taxpayer)
        db.session.commit()

        doc = LpgDocument()
        doc.taxpayer_id = taxpayer.id
        doc.coe = "330230101658"
        doc.estado = "AC"
        doc.tipo_documento = "LPG"
        doc.raw_data = SAMPLE_RAW_DATA
        db.session.add(doc)
        db.session.commit()

        builder = DatosLimpiosBuilder()
        builder.process_document(doc)

        refreshed = db.session.get(LpgDocument, doc.id)
        assert refreshed.datos_limpios is not None
        assert refreshed.datos_limpios["descGrano"] == "TRIGO PAN"
