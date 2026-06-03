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
        "dias_extraccion": t.scheduler_dias_extraccion,
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
            f"La empresa con id {taxpayer_id} no fue encontrada.",
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
                "Tenés que elegir al menos un día.",
                422,
            )
        invalidos = [d for d in dias if not isinstance(d, str) or d not in DIAS_VALIDOS]
        if invalidos:
            return _error(
                "dias_semana_invalido",
                "Hay un día inválido en la selección.",
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
                "La hora debe tener formato HH:MM.",
                422,
                detalle={"recibido": hora},
            )
        t.scheduler_hora_local = hora

    if "dias_extraccion" in payload:
        val = payload["dias_extraccion"]
        # bool es subclase de int; rechazar explícitamente.
        if isinstance(val, bool) or not isinstance(val, int) or val < 1 or val > 366:
            return _error(
                "validacion_fallida",
                "El período debe estar entre 1 y 366 días.",
                422,
                detalle={"recibido": val},
            )
        t.scheduler_dias_extraccion = val

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
            f"La empresa con id {taxpayer_id} no fue encontrada.",
            404,
        )

    if not t.activo:
        return _error(
            "taxpayer_inactivo",
            "La empresa está inactiva. No se puede consultar.",
            409,
            detalle={"taxpayer_id": t.id, "activo": False},
        )

    if not t.scheduler_activo:
        return _error(
            "scheduler_inactivo",
            "La empresa no está programada. Activala antes de consultar manualmente.",
            409,
            detalle={"taxpayer_id": t.id, "scheduler_activo": False},
        )

    try:
        from ..workers.playwright_jobs import run_playwright_pipeline_job
    except ModuleNotFoundError as exc:
        if exc.name == "playwright":
            return _error(
                "playwright_no_instalado",
                "El servicio de consulta no está disponible. Contactá a soporte.",
                503,
            )
        raise

    from ..workers.scheduler_defaults import scheduler_enqueue_kwargs

    enqueue_kwargs = scheduler_enqueue_kwargs(
        t.id,
        dias_extraccion=t.scheduler_dias_extraccion or 90,
    )

    job = ExtractionJob()
    job.taxpayer_id = t.id
    job.operation = SCHEDULER_RUN_NOW_OPERATION
    job.status = "pending"
    job.payload = {**enqueue_kwargs, "headless": True, "trigger": "run_now"}
    db.session.add(job)
    db.session.commit()

    try:
        queue = get_queue()
        rq_job = queue.enqueue(
            run_playwright_pipeline_job,
            extraction_job_id=job.id,
            **enqueue_kwargs,
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
            "No se pudo iniciar la consulta. Reintentá en unos minutos.",
            503,
        )

    job.payload = {
        **(job.payload or {}),
        "queue_name": queue.name,
        "rq_job_id": rq_job.id,
    }
    db.session.commit()

    logger.info(
        "SCHEDULER_RUN_NOW_ENQUEUED | taxpayer_id=%s job_id=%s queue=%s rq_job_id=%s",
        t.id,
        job.id,
        queue.name,
        rq_job.id,
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


@scheduler_bp.patch("/scheduler/bulk")
@require_auth
@require_admin
def bulk_update_scheduler():
    """Aplica la misma configuración a una lista de taxpayers.

    Body esperado:
        {
            "taxpayer_ids": [int, ...],
            "activo": bool (opcional, default true),
            "dias_semana": [str, ...] (opcional),
            "hora_local": "HH:MM" (opcional),
            "dias_extraccion": int (opcional, 1..366)
        }

    Reglas:
    - `taxpayer_ids` no puede estar vacío.
    - Si algún id no existe en DB, devuelve 404 con la lista de ids faltantes.
    - Validaciones de campos idénticas al PATCH unitario.
    - Aplicación atómica: si algún taxpayer falla, hace rollback de todos.
    """
    payload = request.get_json(silent=True) or {}

    ids_raw = payload.get("taxpayer_ids")
    if not isinstance(ids_raw, list) or len(ids_raw) == 0:
        return _error(
            "taxpayer_ids_invalido",
            "Tenés que seleccionar al menos una empresa.",
            422,
        )
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in ids_raw):
        return _error(
            "taxpayer_ids_invalido",
            "Los identificadores de empresa deben ser números enteros.",
            422,
        )

    # Validar campos antes de tocar DB.
    update_fields: dict[str, Any] = {}

    if "activo" in payload:
        update_fields["activo"] = bool(payload["activo"])

    if "dias_semana" in payload:
        dias = payload["dias_semana"]
        if not isinstance(dias, list) or len(dias) == 0:
            return _error(
                "dias_semana_invalido",
                "Tenés que elegir al menos un día.",
                422,
            )
        invalidos = [d for d in dias if not isinstance(d, str) or d not in DIAS_VALIDOS]
        if invalidos:
            return _error(
                "dias_semana_invalido",
                "Hay un día inválido en la selección.",
                422,
                detalle={"invalidos": invalidos},
            )
        update_fields["dias_semana"] = list(dias)

    if "hora_local" in payload:
        hora = payload["hora_local"]
        if not isinstance(hora, str) or not HORA_LOCAL_REGEX.match(hora):
            return _error(
                "hora_local_invalida",
                "La hora debe tener formato HH:MM.",
                422,
                detalle={"recibido": hora},
            )
        update_fields["hora_local"] = hora

    if "dias_extraccion" in payload:
        val = payload["dias_extraccion"]
        if isinstance(val, bool) or not isinstance(val, int) or val < 1 or val > 366:
            return _error(
                "validacion_fallida",
                "El período debe estar entre 1 y 366 días.",
                422,
                detalle={"recibido": val},
            )
        update_fields["dias_extraccion"] = val

    # Resolver taxpayers.
    taxpayers = Taxpayer.query.filter(Taxpayer.id.in_(ids_raw)).all()
    encontrados = {t.id for t in taxpayers}
    faltantes = [i for i in ids_raw if i not in encontrados]
    if faltantes:
        return _error(
            "taxpayers_no_encontrados",
            "Algunas empresas no fueron encontradas.",
            404,
            detalle={"faltantes": faltantes},
        )

    ahora = now_cordoba_naive()
    for t in taxpayers:
        if "activo" in update_fields:
            t.scheduler_activo = update_fields["activo"]
        if "dias_semana" in update_fields:
            t.scheduler_dias_semana = ",".join(update_fields["dias_semana"])
        if "hora_local" in update_fields:
            t.scheduler_hora_local = update_fields["hora_local"]
        if "dias_extraccion" in update_fields:
            t.scheduler_dias_extraccion = update_fields["dias_extraccion"]
        t.updated_at = ahora

    db.session.commit()

    return (
        jsonify(
            {
                "actualizados": [_serialize_scheduler_config(t) for t in taxpayers],
                "total": len(taxpayers),
            }
        ),
        200,
    )


@scheduler_bp.get("/scheduler/taxpayers/<int:taxpayer_id>/last-error-detail")
@require_auth
@require_admin
def get_last_error_detail(taxpayer_id: int):
    """Devuelve el detalle técnico del último ExtractionJob fallido del scheduler
    para un taxpayer. Pensado para el panel admin: muestra la fase y el mensaje
    técnico no traducido para diagnosticar problemas que el usuario final no
    debe ver.
    """
    t = Taxpayer.query.get(taxpayer_id)
    if t is None:
        return _error(
            "taxpayer_no_encontrado",
            f"La empresa con id {taxpayer_id} no fue encontrada.",
            404,
        )

    last_failed = (
        ExtractionJob.query.filter(
            ExtractionJob.taxpayer_id == taxpayer_id,
            ExtractionJob.operation.like("scheduler_%"),
            ExtractionJob.status.in_(("failed", "partial")),
        )
        .order_by(ExtractionJob.finished_at.desc().nullslast(), ExtractionJob.id.desc())
        .first()
    )

    if last_failed is None:
        return (
            jsonify(
                {
                    "taxpayer_id": taxpayer_id,
                    "failure_phase": None,
                    "failure_message_technical": None,
                    "finished_at": None,
                }
            ),
            200,
        )

    return (
        jsonify(
            {
                "taxpayer_id": taxpayer_id,
                "extraction_job_id": last_failed.id,
                "failure_phase": last_failed.failure_phase,
                "failure_message_technical": last_failed.failure_message_technical,
                "finished_at": (
                    last_failed.finished_at.isoformat()
                    if last_failed.finished_at
                    else None
                ),
            }
        ),
        200,
    )
