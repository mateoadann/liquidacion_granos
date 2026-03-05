from __future__ import annotations

from flask import Blueprint, request

from ..extensions import db
from ..models import LpgDocument, Taxpayer

coes_bp = Blueprint("coes", __name__)


def _serialize_coe(doc: LpgDocument, include_taxpayer: bool = False) -> dict:
    result = {
        "id": doc.id,
        "taxpayer_id": doc.taxpayer_id,
        "coe": doc.coe,
        "pto_emision": doc.pto_emision,
        "nro_orden": doc.nro_orden,
        "estado": doc.estado,
        "tipo_documento": doc.tipo_documento,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "raw_data": doc.raw_data,
    }
    if include_taxpayer and doc.taxpayer_id:
        taxpayer = db.session.get(Taxpayer, doc.taxpayer_id)
        if taxpayer:
            result["taxpayer"] = {
                "id": taxpayer.id,
                "empresa": taxpayer.empresa,
                "cuit": taxpayer.cuit,
            }
    return result


@coes_bp.get("/coes")
def list_coes():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)  # Limitar a 100 max

    taxpayer_id = request.args.get("taxpayer_id", type=int)
    estado = request.args.get("estado", type=str)
    fecha_desde = request.args.get("fecha_desde", type=str)
    fecha_hasta = request.args.get("fecha_hasta", type=str)
    search = request.args.get("search", type=str)

    query = db.session.query(LpgDocument)

    if taxpayer_id:
        query = query.filter(LpgDocument.taxpayer_id == taxpayer_id)

    if estado:
        query = query.filter(LpgDocument.estado == estado)

    if fecha_desde:
        query = query.filter(LpgDocument.created_at >= fecha_desde)

    if fecha_hasta:
        query = query.filter(LpgDocument.created_at <= fecha_hasta)

    if search:
        query = query.filter(LpgDocument.coe.ilike(f"%{search}%"))

    total = query.count()
    pages = (total + per_page - 1) // per_page

    coes = (
        query.order_by(LpgDocument.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "coes": [_serialize_coe(c) for c in coes],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@coes_bp.get("/coes/<int:coe_id>")
def get_coe(coe_id: int):
    doc = db.session.get(LpgDocument, coe_id)
    if not doc:
        return {"error": "COE no encontrado"}, 404
    return _serialize_coe(doc, include_taxpayer=True)
