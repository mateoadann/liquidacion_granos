"""Test end-to-end del flujo emisión → carga.

Reproduce el bug detectado en producción (ver docs/spec_fix_emision_v2.md §1):
si el GET /v2/liquidaciones no persiste hash_payload_emitido, el POST
/v1/coes/cargado responde 409 hash_mismatch siempre. Con el fix, el flujo
debe cerrar limpio con 200 ok.
"""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models import CoeEstado, LpgDocument, Taxpayer
from app.services.coe_estado_service import calcular_hash
from app.time_utils import now_cordoba_naive

API_KEY = "test-integration-key"
URL_GET = "/api/v2/liquidaciones"
URL_POST = "/api/v1/coes/cargado"


@pytest.fixture()
def api_headers():
    return {"X-API-Key": API_KEY}


SAMPLE_DATOS = {
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


def _seed_universo(n: int = 3) -> list[str]:
    t = Taxpayer()
    t.cuit = "20304050607"
    t.empresa = "Acopio SA"
    t.cuit_representado = "30711165378"
    t.clave_fiscal_encrypted = "test"
    t.activo = True
    t.scheduler_activo = True
    db.session.add(t)
    db.session.commit()

    coes: list[str] = []
    for i in range(n):
        coe = f"3301000000{i:04d}"
        doc = LpgDocument()
        doc.taxpayer_id = t.id
        doc.coe = coe
        doc.tipo_documento = "LPG"
        doc.datos_limpios = dict(SAMPLE_DATOS)
        db.session.add(doc)
        db.session.commit()

        entry = CoeEstado(
            coe=coe,
            cuit_empresa="30711165378",
            estado="pendiente",
            lpg_document_id=doc.id,
        )
        db.session.add(entry)
        db.session.commit()
        coes.append(coe)
    return coes


def test_emision_carga_e2e_sin_hash_mismatch(client, app, api_headers):
    """GET /v2/liquidaciones → POST /v1/coes/cargado con hash del payload → 200 ok.

    Si el GET sigue siendo read-only (bug original), el POST devuelve 409
    hash_mismatch. Con el fix, devuelve 200 ok y el COE queda 'cargado'.
    """
    with app.app_context():
        coes = _seed_universo(n=3)

    # 1. GET — debe persistir hash_payload_emitido por cada COE
    resp_get = client.get(URL_GET, headers=api_headers)
    assert resp_get.status_code == 200
    body = resp_get.get_json()
    assert len(body["liquidaciones"]) == 3

    # 2. Cada liq tiene su hash calculado contra el payload del response
    liqs_por_coe = {liq["coe"]: liq for liq in body["liquidaciones"]}
    assert set(liqs_por_coe.keys()) == set(coes)

    # 3. Para cada liq, POST cargado con hash computado desde la response
    for coe, liq in liqs_por_coe.items():
        hash_calc = calcular_hash(liq)
        payload = {
            "coe": coe,
            "ejecucion_id": f"exec_{coe}",
            "usuario": "test_user",
            "cargado_en": now_cordoba_naive().isoformat(),
            "estado": "ok",
            "hash_payload": hash_calc,
            "comprobante": {
                "codigo": liq["comprobante"]["codigo"],
                "tipo_pto_vta": liq["comprobante"]["tipo_pto_vta"],
                "nro": liq["comprobante"]["nro"],
                "fecha_emision": liq["comprobante"]["fecha_emision"],
            },
        }
        resp_post = client.post(URL_POST, json=payload, headers=api_headers)

        # ESTE ASSERT es el corazón del fix: sin él, el bug se manifestaría
        # como 409 hash_mismatch porque hash_payload_emitido sería None.
        assert resp_post.status_code == 200, (
            f"POST cargado falló para COE {coe}: "
            f"status={resp_post.status_code} body={resp_post.get_json()}"
        )
        body_post = resp_post.get_json()
        assert body_post["estado"] == "cargado"

    # 4. Verificar persistencia final
    with app.app_context():
        for coe in coes:
            entry = CoeEstado.query.filter_by(coe=coe).first()
            assert entry.estado == "cargado"
            assert entry.hash_payload_emitido is not None
            assert entry.hash_payload_cargado == entry.hash_payload_emitido
