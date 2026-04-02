from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

from ..middleware import require_auth
from ..models import Taxpayer
from ..integrations.arca.client import ArcaConstanciaClient, ArcaDiscoveryConfig, ArcaIntegrationError

logger = logging.getLogger(__name__)

padron_bp = Blueprint("padron", __name__)


@padron_bp.get("/padron/<cuit>")
@require_auth
def get_persona(cuit: str):
    """Consulta datos de un contribuyente en el padrón AFIP usando los certificados del cliente."""
    if not cuit or not cuit.isdigit() or len(cuit) != 11:
        return jsonify({"error": "CUIT inválido, debe ser 11 dígitos"}), 400

    taxpayer_id = request.args.get("taxpayer_id", type=int)
    if not taxpayer_id:
        return jsonify({"error": "Se requiere taxpayer_id"}), 400

    taxpayer = Taxpayer.query.get(taxpayer_id)
    if not taxpayer:
        return jsonify({"error": "Cliente no encontrado"}), 404

    try:
        config = ArcaDiscoveryConfig.from_env()
        config.environment = taxpayer.ambiente or config.environment
        config.cuit_representada = taxpayer.cuit_representado
        config.cert_path = taxpayer.cert_crt_path
        config.key_path = taxpayer.cert_key_path
        ta_base = config.ta_path or os.getenv("ARCA_TA_PATH") or "/tmp/ta"
        config.ta_path = str(Path(ta_base) / f"taxpayer_{taxpayer.id}")

        client = ArcaConstanciaClient(config=config)
        info = client.extract_persona_info(cuit)
        return jsonify(info)
    except ArcaIntegrationError as exc:
        logger.warning("PADRON_LOOKUP_ERROR | cuit=%s taxpayer_id=%s error=%s", cuit, taxpayer_id, exc)
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.exception("PADRON_LOOKUP_UNEXPECTED | cuit=%s taxpayer_id=%s", cuit, taxpayer_id)
        return jsonify({"error": "Error consultando padrón AFIP"}), 500
