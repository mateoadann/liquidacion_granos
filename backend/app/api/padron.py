from __future__ import annotations

import logging

from flask import Blueprint, jsonify

from ..middleware import require_auth
from ..integrations.arca.client import ArcaConstanciaClient, ArcaDiscoveryConfig, ArcaIntegrationError

logger = logging.getLogger(__name__)

padron_bp = Blueprint("padron", __name__)


@padron_bp.get("/padron/<cuit>")
@require_auth
def get_persona(cuit: str):
    """Consulta datos de un contribuyente en el padrón AFIP."""
    if not cuit or not cuit.isdigit() or len(cuit) != 11:
        return jsonify({"error": "CUIT inválido, debe ser 11 dígitos"}), 400

    try:
        config = ArcaDiscoveryConfig.from_env()
        client = ArcaConstanciaClient(config=config)
        info = client.extract_persona_info(cuit)
        return jsonify(info)
    except ArcaIntegrationError as exc:
        logger.warning("PADRON_LOOKUP_ERROR | cuit=%s error=%s", cuit, exc)
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.exception("PADRON_LOOKUP_UNEXPECTED | cuit=%s", cuit)
        return jsonify({"error": "Error consultando padrón AFIP"}), 500
