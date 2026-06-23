from __future__ import annotations

from calendar import monthrange
from datetime import date

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, case, cast, func, or_, String

from ..extensions import db
from ..models import Taxpayer, ExtractionJob, LpgDocument
from ..middleware import require_auth
from ..time_utils import now_cordoba_naive
from ..services.lpg_document_utils import fecha_liquidacion_expr, fecha_liquidacion_as_date

stats_bp = Blueprint("stats", __name__)


@stats_bp.get("/stats")
@require_auth
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

    jobs_partial = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "partial"
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
        "jobs_partial": jobs_partial,
        "jobs_pending": jobs_pending,
        "jobs_running": jobs_running,
        "coes_total": coes_total,
        "last_job": last_job_data,
    }), 200


@stats_bp.get("/stats/mensual")
@require_auth
def get_stats_mensual():
    """Retorna estadisticas mensuales: COEs nuevos y extracciones exitosas del mes.

    Query params:
      mes  — int 1-12  (default: mes actual en America/Argentina/Cordoba)
      anio — int YYYY  (default: año actual en America/Argentina/Cordoba)

    Returns:
      { "mes": int, "anio": int, "coes_nuevos": int, "extracciones_exitosas": int }
    """
    now = now_cordoba_naive()
    current_month = now.month
    current_year = now.year

    mes_raw = request.args.get("mes")
    anio_raw = request.args.get("anio")

    if mes_raw is not None:
        try:
            mes = int(mes_raw)
        except ValueError:
            return jsonify({"error": "El parámetro 'mes' debe ser un entero"}), 400
        if not 1 <= mes <= 12:
            return jsonify({"error": "El parámetro 'mes' debe estar entre 1 y 12"}), 400
    else:
        mes = current_month

    if anio_raw is not None:
        try:
            anio = int(anio_raw)
        except ValueError:
            return jsonify({"error": "El parámetro 'anio' debe ser un entero"}), 400
        if not 1900 <= anio <= 2100:
            return jsonify({"error": "El parámetro 'anio' debe estar entre 1900 y 2100"}), 400
    else:
        anio = current_year

    # Month boundaries: [first_day, first_day_of_next_month)
    first_day = date(anio, mes, 1)
    last_day_num = monthrange(anio, mes)[1]
    last_day = date(anio, mes, last_day_num)
    # Exclusive upper bound for datetime comparisons on finished_at
    if mes == 12:
        next_month_first = date(anio + 1, 1, 1)
    else:
        next_month_first = date(anio, mes + 1, 1)

    # COEs nuevos: count LpgDocument whose emission date (fechaLiquidacion) falls
    # within the selected month, joined to active taxpayers only.
    # We reuse the exact same fecha_liquidacion_expr() + fecha_liquidacion_as_date()
    # that the /coes list endpoint uses for its fecha_desde/fecha_hasta filter,
    # so the month boundaries here are semantically identical to what that page shows.
    fecha_liq_expr = fecha_liquidacion_expr()
    fecha_liq_date = fecha_liquidacion_as_date(fecha_liq_expr)

    # Tipo Cte classification — same source of truth as the /coes filter
    # (coes.py): AJUSTE -> NL, codTipoOperacion == 2 -> F2, else -> F1.
    cod_col = cast(LpgDocument.datos_limpios["codTipoOperacion"], String)
    is_ajuste = LpgDocument.tipo_documento == "AJUSTE"
    is_cod2 = or_(cod_col == "2", cod_col == '"2"')
    is_f2 = and_(~is_ajuste, is_cod2)
    is_f1 = and_(~is_ajuste, or_(cod_col.is_(None), ~is_cod2))

    coes_row = (
        db.session.query(
            func.count(LpgDocument.id),
            func.coalesce(func.sum(case((is_f1, 1), else_=0)), 0),
            func.coalesce(func.sum(case((is_f2, 1), else_=0)), 0),
            func.coalesce(func.sum(case((is_ajuste, 1), else_=0)), 0),
        )
        .join(Taxpayer, Taxpayer.id == LpgDocument.taxpayer_id)
        .filter(Taxpayer.activo.is_(True))
        .filter(fecha_liq_date >= first_day)
        .filter(fecha_liq_date <= last_day)
        .one()
    )
    coes_nuevos = coes_row[0] or 0
    coes_f1 = coes_row[1] or 0
    coes_f2 = coes_row[2] or 0
    coes_nl = coes_row[3] or 0

    # Extracciones exitosas: ExtractionJob with status="completed" and finished_at
    # within [first_day 00:00:00, next_month_first 00:00:00).
    extracciones_exitosas = (
        db.session.query(func.count(ExtractionJob.id))
        .filter(ExtractionJob.status == "completed")
        .filter(ExtractionJob.finished_at >= first_day)
        .filter(ExtractionJob.finished_at < next_month_first)
        .scalar()
    ) or 0

    # Extracciones fallidas del mes: status="failed", mismo rango sobre finished_at.
    extracciones_fallidas = (
        db.session.query(func.count(ExtractionJob.id))
        .filter(ExtractionJob.status == "failed")
        .filter(ExtractionJob.finished_at >= first_day)
        .filter(ExtractionJob.finished_at < next_month_first)
        .scalar()
    ) or 0

    return jsonify({
        "mes": mes,
        "anio": anio,
        "coes_nuevos": coes_nuevos,
        "coes_f1": coes_f1,
        "coes_f2": coes_f2,
        "coes_nl": coes_nl,
        "extracciones_exitosas": extracciones_exitosas,
        "extracciones_fallidas": extracciones_fallidas,
    }), 200
