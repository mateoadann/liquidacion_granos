from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import ExtractionJob, Taxpayer

jobs_bp = Blueprint("jobs", __name__)

ALLOWED_JOB_STATUS = {"pending", "running", "completed", "failed"}


def _serialize_job(item: ExtractionJob) -> dict:
    return {
        "id": item.id,
        "taxpayer_id": item.taxpayer_id,
        "operation": item.operation,
        "status": item.status,
        "payload": item.payload,
        "result": item.result,
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@jobs_bp.get("/jobs")
def list_jobs():
    query = ExtractionJob.query.order_by(ExtractionJob.created_at.desc())

    taxpayer_id = request.args.get("taxpayer_id", type=int)
    if taxpayer_id:
        query = query.filter(ExtractionJob.taxpayer_id == taxpayer_id)

    status = request.args.get("status")
    if status:
        query = query.filter(ExtractionJob.status == status)

    limit = request.args.get("limit", default=100, type=int)
    limit = max(1, min(limit, 500))

    items = query.limit(limit).all()
    return jsonify([_serialize_job(item) for item in items])


@jobs_bp.post("/jobs")
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

    item = ExtractionJob(
        taxpayer_id=taxpayer_id,
        operation=operation,
        status="pending",
        payload=payload.get("payload"),
    )
    db.session.add(item)
    db.session.commit()

    return jsonify(_serialize_job(item)), 201


@jobs_bp.get("/jobs/<int:job_id>")
def get_job(job_id: int):
    item = ExtractionJob.query.get_or_404(job_id)
    return jsonify(_serialize_job(item))


@jobs_bp.patch("/jobs/<int:job_id>")
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
            item.started_at = datetime.utcnow()
        if status in {"completed", "failed"}:
            item.finished_at = datetime.utcnow()

    if "result" in payload:
        item.result = payload["result"]

    if "error_message" in payload:
        item.error_message = payload["error_message"]

    if "payload" in payload:
        item.payload = payload["payload"]

    item.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_job(item))

