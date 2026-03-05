from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import func

from ..extensions import db
from ..models import Taxpayer, ExtractionJob, LpgDocument

stats_bp = Blueprint("stats", __name__)


@stats_bp.get("/stats")
def get_stats():
    """Retorna estadisticas agregadas del sistema."""
    # Clientes
    clients_active = db.session.query(func.count(Taxpayer.id)).filter(
        Taxpayer.activo == True
    ).scalar() or 0

    clients_inactive = db.session.query(func.count(Taxpayer.id)).filter(
        Taxpayer.activo == False
    ).scalar() or 0

    clients_total = clients_active + clients_inactive

    # Jobs
    jobs_total = db.session.query(func.count(ExtractionJob.id)).scalar() or 0

    jobs_completed = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "completed"
    ).scalar() or 0

    jobs_failed = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "failed"
    ).scalar() or 0

    jobs_pending = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "pending"
    ).scalar() or 0

    jobs_running = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "running"
    ).scalar() or 0

    # Ultimo job
    last_job = db.session.query(ExtractionJob).order_by(
        ExtractionJob.created_at.desc()
    ).first()

    last_job_data = None
    if last_job:
        last_job_data = {
            "id": last_job.id,
            "taxpayer_id": last_job.taxpayer_id,
            "operation": last_job.operation,
            "status": last_job.status,
            "created_at": last_job.created_at.isoformat() if last_job.created_at else None,
            "started_at": last_job.started_at.isoformat() if last_job.started_at else None,
            "finished_at": last_job.finished_at.isoformat() if last_job.finished_at else None,
            "error_message": last_job.error_message,
        }

    # COEs
    coes_total = db.session.query(func.count(LpgDocument.id)).scalar() or 0

    return jsonify({
        "clients_active": clients_active,
        "clients_inactive": clients_inactive,
        "clients_total": clients_total,
        "jobs_total": jobs_total,
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        "jobs_pending": jobs_pending,
        "jobs_running": jobs_running,
        "coes_total": coes_total,
        "last_job": last_job_data,
    }), 200
