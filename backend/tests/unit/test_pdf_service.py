from __future__ import annotations

import base64
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.lpg_document import LpgDocument
from app.models.pdf_cache import PdfCache
from app.models.taxpayer import Taxpayer
from app.services.pdf_service import (
    PDF_CACHE_TTL_HOURS,
    PdfFetchError,
    PdfNoCertificatesError,
    PdfNotFoundError,
    get_or_fetch_pdf,
)
from app.time_utils import now_cordoba_naive


def _create_taxpayer(with_certs: bool = True) -> Taxpayer:
    tp = Taxpayer(
        cuit="20304050607",
        empresa="Test SA",
        cuit_representado="30711165378",
        clave_fiscal_encrypted="",
        ambiente="homologacion",
    )
    if with_certs:
        tp.cert_crt_path = "/tmp/test.crt"
        tp.cert_key_path = "/tmp/test.key"
    db.session.add(tp)
    db.session.flush()
    return tp


def _create_document(taxpayer: Taxpayer, tipo: str = "LPG", coe: str = "330230384112") -> LpgDocument:
    doc = LpgDocument(
        taxpayer_id=taxpayer.id,
        coe=coe,
        tipo_documento=tipo,
        estado="AC",
    )
    db.session.add(doc)
    db.session.flush()
    return doc


FAKE_PDF = b"fake pdf content"
FAKE_PDF_B64 = base64.b64encode(FAKE_PDF).decode()

WSLPG_PATCH = "app.integrations.arca.client.ArcaWslpgClient"
CONFIG_PATCH = "app.integrations.arca.client.ArcaDiscoveryConfig"


def _mock_wslpg(pdf_value=FAKE_PDF_B64):
    """Return a mock ArcaWslpgClient class whose instances return pdf_value."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    mock_instance.call_liquidacion_x_coe.return_value = {"data": {"pdf": pdf_value}}
    mock_instance.call_ajuste_x_coe.return_value = {"data": {"pdf": pdf_value}}
    return mock_cls, mock_instance


def _mock_config():
    """Return a mock ArcaDiscoveryConfig class."""
    mock_cls = MagicMock()
    mock_config_inst = MagicMock()
    mock_config_inst.ta_path = "/tmp/ta"
    mock_cls.from_env.return_value = mock_config_inst
    return mock_cls


class TestPdfServiceCacheHit:
    def test_cache_hit_returns_cached_pdf(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            doc = _create_document(tp)
            cache = PdfCache(
                lpg_document_id=doc.id,
                pdf_base64=FAKE_PDF_B64,
                created_at=now_cordoba_naive(),
            )
            db.session.add(cache)
            db.session.commit()

            with patch(WSLPG_PATCH) as mock_ws:
                pdf_bytes, filename = get_or_fetch_pdf(doc.id)

                assert pdf_bytes == FAKE_PDF
                assert filename == f"liquidacion_{doc.coe}.pdf"
                mock_ws.assert_not_called()


class TestPdfServiceCacheMiss:
    def test_cache_miss_fetches_from_wslpg(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            doc = _create_document(tp)
            db.session.commit()

            mock_ws_cls, mock_ws_inst = _mock_wslpg()

            with patch(WSLPG_PATCH, mock_ws_cls), patch(CONFIG_PATCH, _mock_config()):
                pdf_bytes, filename = get_or_fetch_pdf(doc.id)

            assert pdf_bytes == FAKE_PDF
            assert filename == f"liquidacion_{doc.coe}.pdf"
            mock_ws_inst.connect.assert_called_once()
            mock_ws_inst.call_liquidacion_x_coe.assert_called_once_with(
                int(doc.coe), pdf="S"
            )

            # Verify cache was created
            cached = db.session.query(PdfCache).filter_by(lpg_document_id=doc.id).first()
            assert cached is not None
            assert cached.pdf_base64 == FAKE_PDF_B64


class TestPdfServiceExpiredCache:
    def test_expired_cache_refetches(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            doc = _create_document(tp)
            expired_time = now_cordoba_naive() - timedelta(hours=PDF_CACHE_TTL_HOURS + 1)
            old_cache = PdfCache(
                lpg_document_id=doc.id,
                pdf_base64=base64.b64encode(b"old pdf").decode(),
                created_at=expired_time,
            )
            db.session.add(old_cache)
            db.session.commit()

            new_pdf = b"new pdf content"
            new_pdf_b64 = base64.b64encode(new_pdf).decode()
            mock_ws_cls, mock_ws_inst = _mock_wslpg(new_pdf_b64)

            with patch(WSLPG_PATCH, mock_ws_cls), patch(CONFIG_PATCH, _mock_config()):
                pdf_bytes, _ = get_or_fetch_pdf(doc.id)

            assert pdf_bytes == new_pdf
            mock_ws_inst.connect.assert_called_once()

            # Old cache should be replaced
            caches = db.session.query(PdfCache).filter_by(lpg_document_id=doc.id).all()
            assert len(caches) == 1
            assert caches[0].pdf_base64 == new_pdf_b64


class TestPdfServiceErrors:
    def test_not_found_raises(self, app):
        with app.app_context():
            with pytest.raises(PdfNotFoundError):
                get_or_fetch_pdf(99999)

    def test_no_certificates_raises(self, app):
        with app.app_context():
            tp = _create_taxpayer(with_certs=False)
            doc = _create_document(tp)
            db.session.commit()

            with pytest.raises(PdfNoCertificatesError):
                get_or_fetch_pdf(doc.id)

    def test_wslpg_empty_pdf_raises(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            doc = _create_document(tp)
            db.session.commit()

            mock_ws_cls, _ = _mock_wslpg(pdf_value=None)

            with patch(WSLPG_PATCH, mock_ws_cls), patch(CONFIG_PATCH, _mock_config()):
                with pytest.raises(PdfFetchError):
                    get_or_fetch_pdf(doc.id)


class TestPdfServiceDocumentType:
    def test_ajuste_uses_correct_method(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            doc = _create_document(tp, tipo="AJUSTE")
            db.session.commit()

            mock_ws_cls, mock_ws_inst = _mock_wslpg()

            with patch(WSLPG_PATCH, mock_ws_cls), patch(CONFIG_PATCH, _mock_config()):
                get_or_fetch_pdf(doc.id)

            mock_ws_inst.call_ajuste_x_coe.assert_called_once_with(
                int(doc.coe), pdf="S"
            )
            mock_ws_inst.call_liquidacion_x_coe.assert_not_called()
