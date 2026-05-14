from __future__ import annotations

import logging
import re
from typing import Any

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..middleware import require_auth, require_admin
from ..models import ExtractionJob, Taxpayer
from ..queue import get_queue
from ..time_utils import now_cordoba_naive

scheduler_bp = Blueprint("scheduler", __name__)
logger = logging.getLogger(__name__)

DIAS_VALIDOS = {"lun", "mar", "mie", "jue", "vie", "sab", "dom"}
HORA_LOCAL_REGEX = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SCHEDULER_RUN_NOW_OPERATION = "scheduler_run_now"
MAX_ERROR_RECIENTE = 50


def _error(error: str, mensaje: str, status_code: int, detalle: dict | None = None):
    body: dict[str, Any] = {"error": error, "mensaje": mensaje}
    if detalle is not None:
        body["detalle"] = detalle
    return jsonify(body), status_code


def _dias_semana_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _serialize_scheduler_config(t: Taxpayer) -> dict:
    return {
        "taxpayer_id": t.id,
        "activo": bool(t.scheduler_activo),
        "dias_semana": _dias_semana_to_list(t.scheduler_dias_semana),
        "hora_local": t.scheduler_hora_local,
        "ultimo_scrape_ok": (
            t.scheduler_ultimo_ok.isoformat() if t.scheduler_ultimo_ok else None
        ),
        "ultimo_scrape_error": t.scheduler_ultimo_error,
    }


@scheduler_bp.patch("/taxpayers/<int:taxpayer_id>/scheduler")
@require_auth
@require_admin
def update_taxpayer_scheduler(taxpayer_id: int):
    t = Taxpayer.query.get(taxpayer_id)
    if t is None:
        return _error(
            "taxpayer_no_encontrado",
            f"No existe taxpayer con id {taxpayer_id}.",
            404,
        )

    payload = request.get_json(silent=True) or {}

    if "activo" in payload:
        t.scheduler_activo = bool(payload["activo"])

    if "dias_semana" in payload:
        dias = payload["dias_semana"]
        if not isinstance(dias, list):
            return _error(
                "dias_semana_invalido",
                "dias_semana debe ser una lista.",
                422,
            )
        invalidos = [d for d in dias if not isinstance(d, str) or d not in DIAS_VALIDOS]
        if invalidos:
            return _error(
                "dias_semana_invalido",
                "Algún día no es válido. Valores aceptados: lun, mar, mie, jue, vie, sab, dom.",
                422,
                detalle={"invalidos": invalidos},
            )
        # Normalizar manteniendo orden recibido
        t.scheduler_dias_semana = ",".join(dias)

    if "hora_local" in payload:
        hora = payload["hora_local"]
        if not isinstance(hora, str) or not HORA_LOCAL_REGEX.match(hora):
            return _error(
                "hora_local_invalida",
                "hora_local debe tener formato HH:MM (24h).",
                422,
                detalle={"recibido": hora},
            )
        t.scheduler_hora_local = hora

    t.updated_at = now_cordoba_naive()
    db.session.commit()

    return jsonify(_serialize_scheduler_config(t)), 200


@scheduler_bp.post("/scheduler/run-now/<int:taxpayer_id>")
@require_auth
@require_admin
def run_scheduler_now(taxpayer_id: int):
    t = Taxpayer.query.get(taxpayer_id)
    if t is None:
        return _error(
            "taxpayer_no_encontrado",
            f"No existe taxpayer con id {taxpayer_id}.",
            404,
        )

    if not t.activo:
        return _error(
            "taxpayer_inactivo",
            "El taxpayer está marcado como inactivo. No se puede disparar la extracción.",
            409,
            detalle={"taxpayer_id": t.id, "activo": False},
        )

    if not t.scheduler_activo:
        return _error(
            "scheduler_inactivo",
            "El scheduler del taxpayer está desactivado. Activalo antes de disparar manualmente.",
            409,
            detalle={"taxpayer_id": t.id, "scheduler_activo": False},
        )

    job = ExtractionJob()
    job.taxpayer_id = t.id
    job.operation = SCHEDULER_RUN_NOW_OPERATION
    job.status = "pending"
    job.payload = {"trigger": "run_now", "taxpayer_id": t.id}
    db.session.add(job)
    db.session.commit()

    try:
        from ..workers.playwright_jobs import run_playwright_pipeline_job
    except ModuleNotFoundError as exc:
        if exc.name == "playwright":
            job.status = "failed"
            job.error_message = "Playwright no está instalado en backend."
            job.finished_at = now_cordoba_naive()
            db.session.commit()
            return _error(
                "playwright_no_instalado",
                "Playwright no está instalado en backend.",
                503,
            )
        raise

    try:
        from ..workers.scheduler_defaults import scheduler_enqueue_kwargs

        queue = get_queue()
        queue.enqueue(
            run_playwright_pipeline_job,
            extraction_job_id=job.id,
            **scheduler_enqueue_kwargs(t.id),
        )
    except Exception as exc:
        job.status = "failed"
        job.error_message = f"No se pudo encolar el job manual: {exc}"
        job.finished_at = now_cordoba_naive()
        db.session.commit()
        logger.exception(
            "SCHEDULER_RUN_NOW_ENQUEUE_FAILED | taxpayer_id=%s job_id=%s error=%s",
            t.id,
            job.id,
            exc,
        )
        return _error(
            "encolado_fallido",
            "No se pudo encolar el job manual. Verificá Redis/worker e intentá nuevamente.",
            503,
        )

    logger.info(
        "SCHEDULER_RUN_NOW_ENQUEUED | taxpayer_id=%s job_id=%s",
        t.id,
        job.id,
    )

    return (
        jsonify(
            {
                "taxpayer_id": t.id,
                "extraction_job_id": job.id,
                "estado": "encolado",
            }
        ),
        202,
    )


@scheduler_bp.get("/scheduler/status")
@require_auth
@require_admin
def get_scheduler_status():
    taxpayers_total = (
        db.session.query(func.count(Taxpayer.id))
        .filter(Taxpayer.activo.is_(True))
        .scalar()
        or 0
    )
    taxpayers_activos_en_scheduler = (
        db.session.query(func.count(Taxpayer.id))
        .filter(Taxpayer.activo.is_(True), Taxpayer.scheduler_activo.is_(True))
        .scalar()
        or 0
    )
    ultimo_scrape_global_dt = (
        db.session.query(func.max(Taxpayer.scheduler_ultimo_ok)).scalar()
    )
    ultimo_scrape_global = (
        ultimo_scrape_global_dt.isoformat() if ultimo_scrape_global_dt else None
    )

    con_error_query = (
        Taxpayer.query.filter(Taxpayer.scheduler_ultimo_error.isnot(None))
        .order_by(Taxpayer.scheduler_ultimo_error_en.desc().nullslast())
        .limit(MAX_ERROR_RECIENTE)
        .all()
    )

    con_error_reciente = [
        {
            "taxpayer_id": item.id,
            "empresa": item.empresa,
            "ultimo_scrape_error": item.scheduler_ultimo_error,
            "ultimo_scrape_error_en": (
                item.scheduler_ultimo_error_en.isoformat()
                if item.scheduler_ultimo_error_en
                else None
            ),
        }
        for item in con_error_query
    ]

    return jsonify(
        {
            "taxpayers_total": int(taxpayers_total),
            "taxpayers_activos_en_scheduler": int(taxpayers_activos_en_scheduler),
            "ultimo_scrape_global": ultimo_scrape_global,
            "con_error_reciente": con_error_reciente,
        }
    ), 200
