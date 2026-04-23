from __future__ import annotations

import base64
from unittest.mock import patch

from app.extensions import db
from app.models import Taxpayer, LpgDocument
from app.models.pdf_cache import PdfCache

FAKE_PDF = b"%PDF-1.4 fake pdf content"
FAKE_PDF_B64 = base64.b64encode(FAKE_PDF).decode()


def _create_taxpayer(*, cuit: str = "20111111111", empresa: str = "Test SA") -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.activo = True
    db.session.add(item)
    db.session.commit()
    return item


def _create_coe(*, taxpayer_id: int, coe: str = "123456789012", estado: str = "AC") -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.estado = estado
    doc.tipo_documento = "LPG"
    db.session.add(doc)
    db.session.commit()
    return doc


def _create_cached_pdf(doc: LpgDocument) -> PdfCache:
    cache = PdfCache(
        lpg_document_id=doc.id,
        pdf_base64=FAKE_PDF_B64,
    )
    db.session.add(cache)
    db.session.commit()
    return cache


def test_download_pdf_success(client, auth_headers):
    taxpayer = _create_taxpayer()
    doc = _create_coe(taxpayer_id=taxpayer.id)
    _create_cached_pdf(doc)

    response = client.get(f"/api/coes/{doc.id}/pdf", headers=auth_headers)

    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert "attachment" in response.headers.get("Content-Disposition", "")
    assert f"liquidacion_{doc.coe}.pdf" in response.headers.get("Content-Disposition", "")
    assert response.data == FAKE_PDF


def test_download_pdf_not_found(client, auth_headers):
    response = client.get("/api/coes/99999/pdf", headers=auth_headers)
    assert response.status_code == 404


def test_download_pdf_content_type(client, auth_headers):
    taxpayer = _create_taxpayer()
    doc = _create_coe(taxpayer_id=taxpayer.id)
    _create_cached_pdf(doc)

    response = client.get(f"/api/coes/{doc.id}/pdf", headers=auth_headers)

    assert response.status_code == 200
    assert response.content_type == "application/pdf"


def test_download_pdf_from_cache_no_wslpg_call(client, auth_headers):
    taxpayer = _create_taxpayer()
    doc = _create_coe(taxpayer_id=taxpayer.id)
    _create_cached_pdf(doc)

    with patch("app.integrations.arca.client.ArcaWslpgClient") as mock_ws:
        response = client.get(f"/api/coes/{doc.id}/pdf", headers=auth_headers)

        assert response.status_code == 200
        mock_ws.assert_not_called()


def test_download_pdf_requires_auth(client):
    response = client.get("/api/coes/1/pdf")
    assert response.status_code == 401
