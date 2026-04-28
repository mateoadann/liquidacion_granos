from __future__ import annotations

import base64
import logging
import os
from datetime import timedelta
from pathlib import Path

from ..extensions import db
from ..models.lpg_document import LpgDocument
from ..models.pdf_cache import PdfCache
from ..models.taxpayer import Taxpayer
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)

PDF_CACHE_TTL_HOURS = 24


class PdfNotFoundError(Exception):
    """LpgDocument not found."""


class PdfNoCertificatesError(Exception):
    """Taxpayer has no ARCA certificates configured."""


class PdfFetchError(Exception):
    """Failed to fetch PDF from WSLPG."""


def get_or_fetch_pdf(doc_id: int) -> tuple[bytes, str]:
    """Return (pdf_bytes, filename) for the given LpgDocument id.

    Checks cache first; on miss, fetches from WSLPG and caches the result.
    """
    doc = db.session.get(LpgDocument, doc_id)
    if not doc:
        raise PdfNotFoundError(f"LpgDocument {doc_id} no encontrado")

    coe = doc.coe or "sin_coe"
    filename = f"liquidacion_{coe}.pdf"

    # Check cache (only valid entries within TTL)
    cutoff = now_cordoba_naive() - timedelta(hours=PDF_CACHE_TTL_HOURS)
    cached = (
        db.session.query(PdfCache)
        .filter(PdfCache.lpg_document_id == doc_id, PdfCache.created_at > cutoff)
        .first()
    )
    if cached:
        logger.info("PDF_CACHE_HIT | doc_id=%s coe=%s", doc_id, coe)
        return base64.b64decode(cached.pdf_base64), filename

    # Cache miss — lazy cleanup of expired entries
    db.session.query(PdfCache).filter(PdfCache.lpg_document_id == doc_id).delete()
    db.session.flush()

    # Get taxpayer and validate certificates
    taxpayer = db.session.get(Taxpayer, doc.taxpayer_id)
    if not taxpayer or not taxpayer.cert_crt_path or not taxpayer.cert_key_path:
        raise PdfNoCertificatesError(
            f"Taxpayer {doc.taxpayer_id} no tiene certificados ARCA configurados"
        )

    # Initialize WSLPG client — same pattern as coes.py refetch_ajustes
    from ..integrations.arca.client import ArcaWslpgClient, ArcaDiscoveryConfig

    config = ArcaDiscoveryConfig.from_env()
    config.environment = taxpayer.ambiente or config.environment
    config.cuit_representada = taxpayer.cuit_representado
    config.cert_path = taxpayer.cert_crt_path
    config.key_path = taxpayer.cert_key_path
    ta_base = config.ta_path or os.getenv("ARCA_TA_PATH") or "/tmp/ta"
    config.ta_path = str(Path(ta_base) / f"taxpayer_{taxpayer.id}")

    ws_client = ArcaWslpgClient(config=config)
    ws_client.connect()

    # Call WSLPG based on document type
    coe_int = int(doc.coe) if doc.coe else 0
    if doc.tipo_documento == "AJUSTE":
        result = ws_client.call_ajuste_x_coe(coe_int, pdf="S")
    else:
        result = ws_client.call_liquidacion_x_coe(coe_int, pdf="S")

    # Extract PDF from response
    pdf_raw = (result.get("data") or {}).get("pdf") if isinstance(result, dict) else None
    if not pdf_raw:
        raise PdfFetchError(
            f"WSLPG no devolvió PDF para doc_id={doc_id} coe={coe}"
        )

    # The ARCA client normalizes bytes to base64 strings via _normalize_json_safe.
    # Handle both bytes (direct zeep) and base64 string (after normalization).
    if isinstance(pdf_raw, bytes):
        pdf_bytes = pdf_raw
        pdf_b64_str = base64.b64encode(pdf_raw).decode("ascii")
    else:
        # base64-encoded string
        pdf_b64_str = pdf_raw
        pdf_bytes = base64.b64decode(pdf_raw)

    # Store in cache
    cache = PdfCache(lpg_document_id=doc.id, pdf_base64=pdf_b64_str)
    db.session.add(cache)
    db.session.commit()

    logger.info("PDF_CACHE_STORED | doc_id=%s coe=%s", doc_id, coe)
    return pdf_bytes, filename
