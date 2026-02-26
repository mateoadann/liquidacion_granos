from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Taxpayer

taxpayers_bp = Blueprint("taxpayers", __name__)


def _serialize_taxpayer(item: Taxpayer) -> dict:
    return {
        "id": item.id,
        "cuit": item.cuit,
        "razon_social": item.razon_social,
        "ambiente": item.ambiente,
        "activo": item.activo,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _validate_cuit(cuit: str | None) -> bool:
    return bool(cuit and len(cuit) == 11 and cuit.isdigit())


@taxpayers_bp.get("/taxpayers")
def list_taxpayers():
    only_active = request.args.get("active")
    query = Taxpayer.query.order_by(Taxpayer.id.asc())

    if only_active in {"true", "1", "yes"}:
        query = query.filter(Taxpayer.activo.is_(True))
    elif only_active in {"false", "0", "no"}:
        query = query.filter(Taxpayer.activo.is_(False))

    return jsonify([_serialize_taxpayer(item) for item in query.all()])


@taxpayers_bp.post("/taxpayers")
def create_taxpayer():
    payload = request.get_json(silent=True) or {}
    cuit = str(payload.get("cuit", "")).strip()

    if not _validate_cuit(cuit):
        return jsonify({"error": "CUIT inválida. Debe tener 11 dígitos."}), 400

    ambiente = payload.get("ambiente", "homologacion")
    if ambiente not in {"homologacion", "produccion"}:
        return jsonify({"error": "Ambiente inválido."}), 400

    if Taxpayer.query.filter_by(cuit=cuit).first():
        return jsonify({"error": "La CUIT ya existe."}), 409

    item = Taxpayer(
        cuit=cuit,
        razon_social=payload.get("razon_social"),
        ambiente=ambiente,
        activo=bool(payload.get("activo", True)),
    )
    db.session.add(item)
    db.session.commit()

    return jsonify(_serialize_taxpayer(item)), 201


@taxpayers_bp.get("/taxpayers/<int:taxpayer_id>")
def get_taxpayer(taxpayer_id: int):
    item = Taxpayer.query.get_or_404(taxpayer_id)
    return jsonify(_serialize_taxpayer(item))


@taxpayers_bp.patch("/taxpayers/<int:taxpayer_id>")
def update_taxpayer(taxpayer_id: int):
    item = Taxpayer.query.get_or_404(taxpayer_id)
    payload = request.get_json(silent=True) or {}

    if "razon_social" in payload:
        item.razon_social = payload["razon_social"]

    if "ambiente" in payload:
        if payload["ambiente"] not in {"homologacion", "produccion"}:
            return jsonify({"error": "Ambiente inválido."}), 400
        item.ambiente = payload["ambiente"]

    if "activo" in payload:
        item.activo = bool(payload["activo"])

    item.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_taxpayer(item))

