from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import ExtractionJob, Taxpayer
from ..middleware import require_auth
from ..queue import get_queue
from ..time_utils import now_cordoba_naive

playwright_bp = Blueprint("playwright", __name__)
logger = logging.getLogger(__name__)

PLAYWRIGHT_OPERATION = "playwright_lpg_run"
ALLOWED_JOB_STATUS = {"pending", "running", "completed", "failed", "partial"}


def _error(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def _serialize_job(item: ExtractionJob) -> dict:
    return {
        "id": item.id,
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
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _parse_date(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} es obligatorio (DD/MM/AAAA).")
    text = value.strip()
    try:
        parsed = datetime.strptime(text, "%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(
            f"{field} inválida: '{text}'. Formato esperado DD/MM/AAAA."
        ) from exc
    return parsed.strftime("%d/%m/%Y")


def _parse_int_list(field: str, value: object | None) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field} debe ser una lista de enteros.")
    result: list[int] = []
    seen: set[int] = set()
    for item in value:
        if not isinstance(item, int):
            raise ValueError(f"{field} debe contener solo enteros.")
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _parse_and_validate_run_payload(payload: dict) -> dict:
    fecha_desde = _parse_date("fecha_desde", payload.get("fecha_desde"))
    fecha_hasta = _parse_date("fecha_hasta", payload.get("fecha_hasta"))
    taxpayer_ids = _parse_int_list("taxpayer_ids", payload.get("taxpayer_ids"))
    timeout_ms = int(payload.get("timeout_ms", 30000))
    type_delay_ms = int(payload.get("type_delay_ms", 80))
    slow_mo_ms = int(payload.get("slow_mo_ms", 0))
    post_action_delay_ms = int(payload.get("post_action_delay_ms", 0))
    login_max_retries = int(payload.get("login_max_retries", 2))
    # Resilience parameters
    humanize_delays = bool(payload.get("humanize_delays", True))
    retry_max_attempts = int(payload.get("retry_max_attempts", 2))
    retry_base_delay_ms = int(payload.get("retry_base_delay_ms", 1000))

    if timeout_ms <= 0:
        raise ValueError("timeout_ms debe ser mayor a 0.")
    if type_delay_ms < 0:
        raise ValueError("type_delay_ms no puede ser negativo.")
    if slow_mo_ms < 0:
        raise ValueError("slow_mo_ms no puede ser negativo.")
    if post_action_delay_ms < 0:
        raise ValueError("post_action_delay_ms no puede ser negativo.")
    if login_max_retries < 1:
        raise ValueError("login_max_retries debe ser al menos 1.")
    if retry_max_attempts < 1:
        raise ValueError("retry_max_attempts debe ser al menos 1.")
    if retry_base_delay_ms < 0:
        raise ValueError("retry_base_delay_ms no puede ser negativo.")

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "taxpayer_ids": taxpayer_ids,
        "timeout_ms": timeout_ms,
        "type_delay_ms": type_delay_ms,
        "slow_mo_ms": slow_mo_ms,
        "post_action_delay_ms": post_action_delay_ms,
        "login_max_retries": login_max_retries,
        "humanize_delays": humanize_delays,
        "retry_max_attempts": retry_max_attempts,
        "retry_base_delay_ms": retry_base_delay_ms,
    }


def _create_and_enqueue_job_for_taxpayer(
    *, taxpayer_id: int, params: dict, run_func, operation: str = PLAYWRIGHT_OPERATION
) -> ExtractionJob:
    """Crea 1 ExtractionJob para 1 taxpayer y lo encola en la queue Playwright.

    Raises:
        Exception: si falla el enqueue (el job queda persistido con status=failed).
    """
    item = ExtractionJob()
    item.taxpayer_id = taxpayer_id
    item.operation = operation
    item.status = "pending"
    item.payload = {
        "fecha_desde": params["fecha_desde"],
        "fecha_hasta": params["fecha_hasta"],
        "taxpayer_ids": [taxpayer_id],
        "timeout_ms": params["timeout_ms"],
        "type_delay_ms": params["type_delay_ms"],
        "slow_mo_ms": params["slow_mo_ms"],
        "post_action_delay_ms": params["post_action_delay_ms"],
        "login_max_retries": params["login_max_retries"],
        "humanize_delays": params["humanize_delays"],
        "retry_max_attempts": params["retry_max_attempts"],
        "retry_base_delay_ms": params["retry_base_delay_ms"],
        "headless": True,
    }
    db.session.add(item)
    db.session.commit()

    try:
        queue = get_queue("playwright")
        rq_job = queue.enqueue(
            run_func,
            extraction_job_id=item.id,
            fecha_desde=params["fecha_desde"],
            fecha_hasta=params["fecha_hasta"],
            taxpayer_ids=[taxpayer_id],
            timeout_ms=params["timeout_ms"],
            type_delay_ms=params["type_delay_ms"],
            slow_mo_ms=params["slow_mo_ms"],
            post_action_delay_ms=params["post_action_delay_ms"],
            login_max_retries=params["login_max_retries"],
            humanize_delays=params["humanize_delays"],
            retry_max_attempts=params["retry_max_attempts"],
            retry_base_delay_ms=params["retry_base_delay_ms"],
            job_timeout=max((params["timeout_ms"] // 1000) * 10, 3600),
            result_ttl=86400,
            failure_ttl=86400,
        )
    except Exception as exc:
        item.status = "failed"
        item.error_message = f"No se pudo encolar el job Playwright: {exc}"
        item.finished_at = now_cordoba_naive()
        db.session.commit()
        logger.exception(
            "JOB_ENQUEUE_FAILED | job_id=%s operation=%s taxpayer_id=%s error=%s",
            item.id,
            operation,
            taxpayer_id,
            exc,
        )
        raise

    item.payload = {
        **(item.payload or {}),
        "queue_name": queue.name,
        "rq_job_id": rq_job.id,
    }
    db.session.commit()

    logger.info(
        "JOB_ENQUEUED | job_id=%s operation=%s taxpayer_id=%s queue=%s rq_job_id=%s",
        item.id,
        operation,
        taxpayer_id,
        queue.name,
        rq_job.id,
    )
    return item


@playwright_bp.post("/playwright/lpg/run")
@require_auth
def enqueue_lpg_playwright_pipeline():
    payload = request.get_json(silent=True) or {}
    try:
        params = _parse_and_validate_run_payload(payload)
    except ValueError as exc:
        return _error(str(exc), 400)

    taxpayer_ids = params["taxpayer_ids"]

    try:
        from ..workers.playwright_jobs import run_playwright_pipeline_job
    except ModuleNotFoundError as exc:
        if exc.name == "playwright":
            return _error(
                (
                    "Playwright no está instalado en backend. "
                    "Instalar con pip y playwright install chromium."
                ),
                503,
            )
        raise

    # Resolve target taxpayer ids: explicit list, or all active+playwright_enabled
    if taxpayer_ids:
        existing_ids = {
            item.id
            for item in Taxpayer.query.filter(Taxpayer.id.in_(taxpayer_ids)).with_entities(Taxpayer.id)
        }
        missing = [item for item in taxpayer_ids if item not in existing_ids]
        if missing:
            return _error(f"taxpayer_ids inexistentes: {missing}", 400)
        target_ids = taxpayer_ids
    else:
        target_ids = [
            t.id
            for t in Taxpayer.query.filter(
                Taxpayer.activo.is_(True), Taxpayer.playwright_enabled.is_(True)
            )
            .order_by(Taxpayer.id.asc())
            .with_entities(Taxpayer.id)
        ]
        if not target_ids:
            return _error("No hay clientes activos con Playwright habilitado.", 400)

    logger.info(
        "JOB_RECEIVED | operation=%s desde=%s hasta=%s taxpayers=%s",
        PLAYWRIGHT_OPERATION,
        params["fecha_desde"],
        params["fecha_hasta"],
        target_ids,
    )

    created_jobs: list[ExtractionJob] = []
    for tp_id in target_ids:
        try:
            job = _create_and_enqueue_job_for_taxpayer(
                taxpayer_id=tp_id, params=params, run_func=run_playwright_pipeline_job
            )
            created_jobs.append(job)
        except Exception:
            # Already persisted as failed inside the helper; keep going so the
            # rest of the taxpayers get a chance. The response will surface the
            # failed job alongside the successful ones.
            failed = ExtractionJob.query.filter_by(
                taxpayer_id=tp_id, operation=PLAYWRIGHT_OPERATION, status="failed"
            ).order_by(ExtractionJob.id.desc()).first()
            if failed is not None:
                created_jobs.append(failed)

    return (
        jsonify(
            {
                "message": f"{len(created_jobs)} extracción(es) Playwright encolada(s).",
                "jobs": [_serialize_job(j) for j in created_jobs],
            }
        ),
        202,
    )


@playwright_bp.get("/playwright/lpg/jobs/<int:job_id>")
@require_auth
def get_lpg_playwright_job(job_id: int):
    item = ExtractionJob.query.get_or_404(job_id)
    if item.operation != PLAYWRIGHT_OPERATION:
        return _error("job_id no corresponde a una corrida Playwright LPG.", 404)
    if item.status not in ALLOWED_JOB_STATUS:
        item.status = "failed"
        item.error_message = item.error_message or "Estado de job inválido."
        db.session.commit()
    return jsonify(_serialize_job(item))


@playwright_bp.post("/playwright/lpg/jobs/<int:job_id>/retry")
@require_auth
def retry_lpg_playwright_job(job_id: int):
    """Reintentar manualmente un job en estado failed.

    Crea un NUEVO ExtractionJob con operation `playwright_lpg_run` (manual),
    el mismo taxpayer y los mismos parámetros del job original. El nuevo job
    queda al final de la queue.
    """
    original = ExtractionJob.query.get_or_404(job_id)

    if original.status != "failed":
        return _error(
            f"Solo se pueden reintentar jobs en estado 'failed'. Estado actual: '{original.status}'.",
            409,
        )

    from ..services.failure_classifier import is_failure_retryable

    if not is_failure_retryable(
        failure_phase=original.failure_phase,
        failure_error_type=original.failure_error_type,
    ):
        return _error(
            "Este tipo de falla no se puede reintentar. "
            "Revisá la configuración del cliente (por ejemplo, la clave fiscal).",
            409,
        )

    payload = dict(original.payload or {})
    fecha_desde = payload.get("fecha_desde")
    fecha_hasta = payload.get("fecha_hasta")
    if not fecha_desde or not fecha_hasta:
        return _error(
            "El job original no tiene fecha_desde/fecha_hasta en su payload — no se puede reintentar.",
            422,
        )

    try:
        from ..workers.playwright_jobs import run_playwright_pipeline_job
    except ModuleNotFoundError as exc:
        if exc.name == "playwright":
            return _error(
                "Playwright no está instalado en backend.",
                503,
            )
        raise

    # Build params dict reusing the original payload, fall back to safe defaults.
    params = {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "timeout_ms": int(payload.get("timeout_ms", 30000)),
        "type_delay_ms": int(payload.get("type_delay_ms", 80)),
        "slow_mo_ms": int(payload.get("slow_mo_ms", 0)),
        "post_action_delay_ms": int(payload.get("post_action_delay_ms", 0)),
        "login_max_retries": int(payload.get("login_max_retries", 2)),
        "humanize_delays": bool(payload.get("humanize_delays", True)),
        "retry_max_attempts": int(payload.get("retry_max_attempts", 2)),
        "retry_base_delay_ms": int(payload.get("retry_base_delay_ms", 1000)),
    }

    try:
        new_job = _create_and_enqueue_job_for_taxpayer(
            taxpayer_id=original.taxpayer_id,
            params=params,
            run_func=run_playwright_pipeline_job,
        )
        # Tag the new job's payload so the UI can trace it back to the original.
        new_job.payload = {
            **(new_job.payload or {}),
            "retry_of_job_id": original.id,
        }
        db.session.commit()
    except Exception:
        return _error(
            "No se pudo encolar el reintento. Verificá Redis/worker e intentá nuevamente.",
            503,
        )

    return (
        jsonify(
            {
                "message": "Reintento encolado.",
                "job": _serialize_job(new_job),
            }
        ),
        202,
    )
