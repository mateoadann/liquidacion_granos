from __future__ import annotations

from app.extensions import db
from app.models import LpgDocument, Taxpayer


def _create_taxpayer(*, cuit: str = "20304050607", cuit_representado: str = "30711165378", empresa: str = "Acopio SA") -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit_representado
    item.clave_fiscal_encrypted = "test"
    item.activo = True
    db.session.add(item)
    db.session.commit()
    return item


def _create_doc(
    *,
    taxpayer_id: int,
    coe: str = "330230384112",
    tipo_documento: str = "LPG",
    datos_limpios: dict | None = None,
) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.tipo_documento = tipo_documento
    doc.datos_limpios = datos_limpios
    db.session.add(doc)
    db.session.commit()
    return doc


def _export_url(client_id: int) -> str:
    return f"/api/clients/{client_id}/export/json-v7"


SAMPLE_DATOS_LIMPIOS = {
    "codTipoOperacion": 2,
    "coe": "330230384112",
    "fechaLiquidacion": "2026-02-26",
    "cuitComprador": 30502874353,
    "cuitVendedor": 30502874353,
    "codGrano": 15,
    "precioOperacion": 205.6,
    "totalPesoNeto": 38193.0,
    "subTotal": 7852593.91,
    "importeIva": 824522.36,
    "operacionConIva": 8677116.27,
    "retenciones": [
        {
            "codigoConcepto": "RI",
            "importeRetencion": 628207.51,
            "alicuota": 8.0,
            "baseCalculo": 7852593.91,
            "descConcepto": "Retencion IVA",
        },
        {
            "codigoConcepto": "IB",
            "importeRetencion": 200000.0,
            "alicuota": 4.0,
            "baseCalculo": 5000000.0,
            "descConcepto": "IIBB Origen",
        },
        {
            "codigoConcepto": "OG",
            "importeRetencion": 127489.77,
            "alicuota": 4.0,
            "baseCalculo": 3187244.25,
            "descConcepto": "IIBB Destino",
        },
    ],
    "deducciones": [
        {
            "codigoConcepto": "CO",
            "detalleAclaratorio": "Comision",
            "baseCalculo": 95422.07,
            "importeDeduccion": 105441.39,
            "alicuotaIva": 10.5,
            "importeIva": 10019.32,
            "descConcepto": "Comision",
        },
    ],
}


# ─── Success ────────────────────────────────────────────────────────


def test_export_json_v7_success(client, auth_headers):
    taxpayer = _create_taxpayer()
    _create_doc(taxpayer_id=taxpayer.id, datos_limpios=SAMPLE_DATOS_LIMPIOS)

    response = client.get(
        _export_url(taxpayer.id),
        query_string={
            "mes": 2,
            "anio": 2026,
            "fecha_desde": "2026-02-01",
            "fecha_hasta": "2026-02-28",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert "liquidaciones" in body
    assert len(body["liquidaciones"]) == 1

    liq = body["liquidaciones"][0]
    assert liq["mes"] == 2
    assert liq["anio"] == 2026
    assert liq["cuit_empresa"] == "30711165378"  # must be cuit_representado, NOT cuit
    assert liq["cuit_empresa"] != "20304050607"  # must NOT be the login cuit
    assert liq["comprobante"]["codigo"] == "F2"
    assert liq["grano"]["cod_grano"] == 15
    assert liq["grano"]["precio_unitario"] == 205.6
    assert liq["grano"]["cantidad_kg"] == 38193


# ─── Not found ──────────────────────────────────────────────────────


def test_export_json_v7_not_found(client, auth_headers):
    response = client.get(
        _export_url(99999),
        query_string={"mes": 2, "anio": 2026},
        headers=auth_headers,
    )

    assert response.status_code == 404
    body = response.get_json()
    assert "error" in body


# ─── Empty result ───────────────────────────────────────────────────


def test_export_json_v7_empty_result(client, auth_headers):
    taxpayer = _create_taxpayer()

    response = client.get(
        _export_url(taxpayer.id),
        query_string={
            "mes": 2,
            "anio": 2026,
            "fecha_desde": "2026-02-01",
            "fecha_hasta": "2026-02-28",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["liquidaciones"] == []
    assert body["schema_version"] == "v7.1"
    assert "meta" in body


# ─── Content-Disposition ────────────────────────────────────────────


def test_export_json_v7_content_disposition(client, auth_headers):
    taxpayer = _create_taxpayer(cuit="30502874353", cuit_representado="30999888777")
    _create_doc(taxpayer_id=taxpayer.id, datos_limpios=SAMPLE_DATOS_LIMPIOS)

    response = client.get(
        _export_url(taxpayer.id),
        query_string={
            "mes": 2,
            "anio": 2026,
            "fecha_desde": "2026-02-01",
            "fecha_hasta": "2026-02-28",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    cd = response.headers.get("Content-Disposition", "")
    assert "liquidaciones_v7_30999888777_2_2026.json" in cd  # uses cuit_representado
    assert "30502874353" not in cd  # must NOT use login cuit


# ─── Missing mes/anio ──────────────────────────────────────────────


def test_export_json_v7_requires_mes_anio(client, auth_headers):
    taxpayer = _create_taxpayer()

    # Missing both
    response = client.get(
        _export_url(taxpayer.id),
        query_string={},
        headers=auth_headers,
    )
    assert response.status_code == 400
    body = response.get_json()
    assert "mes" in body["error"].lower() or "anio" in body["error"].lower()

    # Missing anio
    response = client.get(
        _export_url(taxpayer.id),
        query_string={"mes": 2},
        headers=auth_headers,
    )
    assert response.status_code == 400

    # Missing mes
    response = client.get(
        _export_url(taxpayer.id),
        query_string={"anio": 2026},
        headers=auth_headers,
    )
    assert response.status_code == 400


# ─── IB + OG unification ───────────────────────────────────────────


def test_export_json_v7_no_og_in_response(client, auth_headers):
    """IB and OG retenciones should be unified into a single IB entry."""
    taxpayer = _create_taxpayer()
    _create_doc(taxpayer_id=taxpayer.id, datos_limpios=SAMPLE_DATOS_LIMPIOS)

    response = client.get(
        _export_url(taxpayer.id),
        query_string={
            "mes": 2,
            "anio": 2026,
            "fecha_desde": "2026-02-01",
            "fecha_hasta": "2026-02-28",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    liq = body["liquidaciones"][0]

    retenciones = liq["retenciones"]
    codigos = [r["codigo_arca"] for r in retenciones]

    # OG should NOT appear as separate entry
    assert "OG" not in codigos

    # IB should appear (unified IB + OG)
    assert "IB" in codigos
    ib_entry = next(r for r in retenciones if r["codigo_arca"] == "IB")

    # Combined importe: 200000.0 (IB) + 127489.77 (OG)
    assert abs(ib_entry["importe"] - 327489.77) < 0.01

    # Combined alicuota: 4.0 (IB) + 4.0 (OG)
    assert abs(ib_entry["alicuota"] - 8.0) < 0.01

    # RI should remain unchanged
    assert "RI" in codigos
