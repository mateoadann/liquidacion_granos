from __future__ import annotations

import io
import base64

from flask import Blueprint, jsonify, request, send_file

from ..extensions import db
from ..models import ExtractionJob, JobScreenshot, Taxpayer
from ..middleware import require_auth
from ..time_utils import now_cordoba_naive

jobs_bp = Blueprint("jobs", __name__)

ALLOWED_JOB_STATUS = {"pending", "running", "completed", "failed", "partial"}


def _extract_coe_count(result: dict | None) -> int:
    if not result or not isinstance(result, dict):
        return 0
    total = 0
    for r in result.get("results", []):
        if not isinstance(r, dict):
            continue
        # Distinguish "key absent" (old job, use fallback) from "key present with 0"
        # (new job where all COEs already existed → must show 0, not detectados).
        if "total_coes_nuevos" in r:
            total += r["total_coes_nuevos"] or 0
        else:
            total += r.get("total_coes_detectados", 0)
    return total


def _serialize_job(item: ExtractionJob) -> dict:
    return {
        "id": item.id,
        "taxpayer_id": item.taxpayer_id,
        "operation": item.operation,
        "status": item.status,
        "current_phase": item.current_phase,
        "current_message": item.current_message,
        "payload": item.payload,
        "result": item.result,
        "error_message": item.error_message,
        "failure_phase": item.failure_phase,
        "failure_message_user": item.failure_message_user,
        "failure_message_technical": item.failure_message_technical,
        "failure_error_type": item.failure_error_type,
        "coe_count": _extract_coe_count(item.result),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@jobs_bp.get("/jobs")
@require_auth
def list_jobs():
    query = ExtractionJob.query.order_by(ExtractionJob.created_at.desc())

    taxpayer_id = request.args.get("taxpayer_id", type=int)
    if taxpayer_id:
        query = query.filter(ExtractionJob.taxpayer_id == taxpayer_id)

    status = request.args.get("status")
    if status:
        query = query.filter(ExtractionJob.status == status)

    # Backward compatible: if caller passes `limit`, behave like before
    # (flat array, no pagination). The dashboard's RecentJobsPanel uses this.
    if "limit" in request.args and "page" not in request.args:
        limit = max(1, min(request.args.get("limit", type=int) or 100, 500))
        items = query.limit(limit).all()
        return jsonify([_serialize_job(item) for item in items])

    page = max(1, request.args.get("page", default=1, type=int))
    per_page = max(1, min(request.args.get("per_page", default=20, type=int), 100))

    total = query.count()
    pages = (total + per_page - 1) // per_page

    items = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        {
            "jobs": [_serialize_job(item) for item in items],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }
    )


@jobs_bp.post("/jobs")
@require_auth
def create_job():
    payload = request.get_json(silent=True) or {}

    taxpayer_id = payload.get("taxpayer_id")
    operation = (payload.get("operation") or "").strip()

    if not taxpayer_id or not isinstance(taxpayer_id, int):
        return jsonify({"error": "taxpayer_id es obligatorio (int)."}), 400

    if not operation:
        return jsonify({"error": "operation es obligatorio."}), 400

    taxpayer = Taxpayer.query.get(taxpayer_id)
    if not taxpayer:
        return jsonify({"error": "taxpayer_id no existe."}), 404

    item = ExtractionJob()
    item.taxpayer_id = taxpayer_id
    item.operation = operation
    item.status = "pending"
    item.payload = payload.get("payload")
    db.session.add(item)
    db.session.commit()

    return jsonify(_serialize_job(item)), 201


@jobs_bp.get("/jobs/<int:job_id>")
@require_auth
def get_job(job_id: int):
    item = ExtractionJob.query.get_or_404(job_id)
    data = _serialize_job(item)
    data["tiene_screenshot"] = (
        JobScreenshot.query.filter_by(extraction_job_id=item.id).first() is not None
    )
    return jsonify(data)


@jobs_bp.get("/jobs/<int:job_id>/screenshot")
@require_auth
def get_job_screenshot(job_id: int):
    shot = (
        JobScreenshot.query.filter_by(extraction_job_id=job_id)
        .order_by(JobScreenshot.id.desc())
        .first()
    )
    if shot is None:
        return {"error": "No hay captura para este job."}, 404
    return send_file(
        io.BytesIO(base64.b64decode(shot.image_base64)),
        mimetype="image/png",
    )


@jobs_bp.patch("/jobs/<int:job_id>")
@require_auth
def update_job(job_id: int):
    item = ExtractionJob.query.get_or_404(job_id)
    payload = request.get_json(silent=True) or {}

    if "status" in payload:
        status = payload["status"]
        if status not in ALLOWED_JOB_STATUS:
            return (
                jsonify(
                    {
                        "error": f"status inválido. Valores permitidos: {sorted(ALLOWED_JOB_STATUS)}"
                    }
                ),
                400,
            )
        item.status = status
        if status == "running" and not item.started_at:
            item.started_at = now_cordoba_naive()
        if status in {"completed", "failed", "partial"}:
            item.finished_at = now_cordoba_naive()

    if "result" in payload:
        item.result = payload["result"]

    if "error_message" in payload:
        item.error_message = payload["error_message"]

    if "payload" in payload:
        item.payload = payload["payload"]

    item.updated_at = now_cordoba_naive()
    db.session.commit()

    return jsonify(_serialize_job(item))
