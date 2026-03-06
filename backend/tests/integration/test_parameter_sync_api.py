from __future__ import annotations

from app.extensions import db
from app.models import WslpgParameter, Taxpayer, LpgDocument


def _create_doc_with_raw_data(taxpayer_id: int) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = "330230101658"
    doc.estado = "AC"
    doc.tipo_documento = "LPG"
    doc.raw_data = {"data": {"codGrano": 15, "codPuerto": 14}}
    db.session.add(doc)
    db.session.commit()
    return doc


def test_rebuild_datos_limpios(client):
    taxpayer = Taxpayer()
    taxpayer.cuit = "20111111111"
    taxpayer.empresa = "Test SA"
    taxpayer.cuit_representado = "20111111111"
    taxpayer.clave_fiscal_encrypted = "x"
    db.session.add(taxpayer)
    db.session.commit()

    doc = _create_doc_with_raw_data(taxpayer.id)

    db.session.add(WslpgParameter(tabla="tipoGrano", codigo="15", descripcion="TRIGO PAN"))
    db.session.add(WslpgParameter(tabla="puerto", codigo="14", descripcion="OTROS"))
    db.session.commit()

    response = client.post("/api/admin/rebuild-datos-limpios")
    assert response.status_code == 200
    data = response.get_json()
    assert data["processed"] == 1

    refreshed = db.session.get(LpgDocument, doc.id)
    assert refreshed.datos_limpios is not None
    assert refreshed.datos_limpios["descGrano"] == "TRIGO PAN"
