from __future__ import annotations

from flask import Blueprint, jsonify

from ..middleware import require_auth
from ..services.extraction_health import compute_health

extracciones_bp = Blueprint("extracciones", __name__)


@extracciones_bp.get("/extracciones/salud")
@require_auth
def get_extracciones_salud():
    """Estado de salud de las extracciones por cliente activo."""
    return jsonify(compute_health())
