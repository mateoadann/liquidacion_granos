from __future__ import annotations

import logging
from typing import Any

from .. import create_app
from ..extensions import db
from ..models import ExtractionJob, Taxpayer
from ..services.extraction_failure_mapper import _truncate, map_failure
from ..services.extraction_phases import ExtractionPhase
from ..services.lpg_playwright_pipeline import (
    LpgPlaywrightPipelineService,
    TaxpayerPipelineResult,
)
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)


def _update_job(job_id: int, **fields: Any) -> None:
    item = ExtractionJob.query.get(job_id)
    if not item:
        logger.error("Playwright worker: job no existe | job_id=%s", job_id)
        return
    for key, value in fields.items():
        setattr(item, key, value)
    item.updated_at = now_cordoba_naive()
    db.session.commit()


def _resolve_taxpayers(taxpayer_ids: list[int] | None) -> list[Taxpayer]:
    query = Taxpayer.query.filter(
        Taxpayer.activo.is_(True), Taxpayer.playwright_enabled.is_(True)
    ).order_by(Taxpayer.id.asc())
    if taxpayer_ids:
        query = query.filter(Taxpayer.id.in_(taxpayer_ids))
    return query.all()


def _build_progress_payload(taxpayers: list[Taxpayer]) -> dict[str, Any]:
    return {
        "total_clients": len(taxpayers),
        "completed_clients": 0,
        "running_client_id": None,
        "clients": [
            {
                "taxpayer_id": item.id,
                "empresa": item.empresa,
                "status": "pending",
                "error": None,
                "started_at": None,
                "finished_at": None,
                "metrics": {
                    "total_coes_detectados": 0,
                    "total_coes_nuevos": 0,
                    "total_procesados_ok": 0,
                    "total_procesados_error": 0,
                },
                "current_phase": None,
                "current_message": None,
                "failure_phase": None,
                "failure_message_user": None,
                "failure_message_technical": None,
            }
            for item in taxpayers
        ],
    }


def _update_progress_state(
    extraction_job_id: int,
    payload: dict[str, Any],
    *,
    taxpayer_id: int,
    status: str,
    error: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    clients = progress.get("clients") if isinstance(progress.get("clients"), list) else []

    for client in clients:
        if not isinstance(client, dict):
            continue
        if client.get("taxpayer_id") != taxpayer_id:
            continue
        now_iso = now_cordoba_naive().isoformat()
        if status == "running":
            client["status"] = "running"
            client["started_at"] = now_iso
            progress["running_client_id"] = taxpayer_id
            client["error"] = None
            client["current_phase"] = None
            client["current_message"] = None
            client["failure_phase"] = None
            client["failure_message_user"] = None
            client["failure_message_technical"] = None
        elif status in {"done", "error"}:
            client["status"] = status
            client["finished_at"] = now_iso
            progress["running_client_id"] = None
            client["error"] = error
            if metrics:
                client["metrics"] = metrics
        break

    completed = sum(
        1
        for client in clients
        if isinstance(client, dict) and client.get("status") in {"done", "error"}
    )
    progress["completed_clients"] = completed
    payload["progress"] = progress
    _update_job(extraction_job_id, payload=payload)


def _update_phase_state(
    extraction_job_id: int,
    payload: dict[str, Any],
    *,
    taxpayer_id: int,
    phase: ExtractionPhase,
    message: str,
) -> None:
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    clients = progress.get("clients") if isinstance(progress.get("clients"), list) else []
    for client in clients:
        if isinstance(client, dict) and client.get("taxpayer_id") == taxpayer_id:
            client["current_phase"] = phase.value
            client["current_message"] = message
            break
    payload["progress"] = progress
    _update_job(
        extraction_job_id,
        payload=payload,
        current_phase=phase.value,
        current_message=message,
    )


def _persist_taxpayer_failure(
    extraction_job_id: int,
    payload: dict[str, Any],
    *,
    taxpayer_id: int,
    phase: ExtractionPhase | None,
    error_type: str,
    dropdown_clicked: bool,
    exception_text: str | None,
) -> tuple[str, str]:
    user_es, tech_en = map_failure(phase, error_type, dropdown_clicked)
    if exception_text:
        tech_combined = _truncate(f"{tech_en} | {exception_text}")
    else:
        tech_combined = _truncate(tech_en)
    phase_value = phase.value if phase else None

    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    clients = progress.get("clients") if isinstance(progress.get("clients"), list) else []
    for client in clients:
        if isinstance(client, dict) and client.get("taxpayer_id") == taxpayer_id:
            client["failure_phase"] = phase_value
            client["failure_message_user"] = user_es
            client["failure_message_technical"] = tech_combined
            break
    payload["progress"] = progress
    return user_es, tech_combined


def run_playwright_pipeline_job(
    *,
    extraction_job_id: int,
    fecha_desde: str,
    fecha_hasta: str,
    taxpayer_ids: list[int] | None,
    timeout_ms: int,
    type_delay_ms: int,
    slow_mo_ms: int = 0,
    post_action_delay_ms: int = 0,
    login_max_retries: int = 2,
    humanize_delays: bool = True,
    retry_max_attempts: int = 2,
    retry_base_delay_ms: int = 1000,
) -> None:
    app = create_app()
    with app.app_context():
        logger.info(
            "JOB_STARTED | job_id=%s operation=playwright_lpg_run desde=%s hasta=%s taxpayers=%s timeout_ms=%s type_delay_ms=%s slow_mo_ms=%s post_action_delay_ms=%s login_max_retries=%s humanize_delays=%s retry_max_attempts=%s retry_base_delay_ms=%s",
            extraction_job_id,
            fecha_desde,
            fecha_hasta,
            taxpayer_ids or "todos",
            timeout_ms,
            type_delay_ms,
            slow_mo_ms,
            post_action_delay_ms,
            login_max_retries,
            humanize_delays,
            retry_max_attempts,
            retry_base_delay_ms,
        )
        _update_job(
            extraction_job_id,
            status="running",
            started_at=now_cordoba_naive(),
            error_message=None,
            current_phase=None,
            current_message=None,
            failure_phase=None,
            failure_message_user=None,
            failure_message_technical=None,
        )

        job_item = ExtractionJob.query.get(extraction_job_id)
        payload = dict(job_item.payload or {}) if job_item else {}
        taxpayers = _resolve_taxpayers(taxpayer_ids)
        payload["progress"] = _build_progress_payload(taxpayers)
        _update_job(extraction_job_id, payload=payload)

        last_taxpayer_failure: dict[str, Any] = {
            "phase": None,
            "user_es": None,
            "tech": None,
        }

        def on_taxpayer_start(taxpayer: Taxpayer) -> None:
            _update_progress_state(
                extraction_job_id,
                payload,
                taxpayer_id=taxpayer.id,
                status="running",
            )

        def on_taxpayer_finish(result: TaxpayerPipelineResult) -> None:
            _update_progress_state(
                extraction_job_id,
                payload,
                taxpayer_id=result.taxpayer_id,
                status="done" if result.ok else "error",
                error=result.error,
                metrics={
                    "total_coes_detectados": result.total_coes_detectados,
                    "total_coes_nuevos": result.total_coes_nuevos,
                    "total_procesados_ok": result.total_procesados_ok,
                    "total_procesados_error": result.total_procesados_error,
                },
            )
            if not result.ok:
                user_es, tech_combined = _persist_taxpayer_failure(
                    extraction_job_id,
                    payload,
                    taxpayer_id=result.taxpayer_id,
                    phase=result.failure_phase,
                    error_type=result.failure_error_type or "unknown",
                    dropdown_clicked=result.failure_dropdown_clicked,
                    exception_text=result.error,
                )
                last_taxpayer_failure["phase"] = (
                    result.failure_phase.value if result.failure_phase else None
                )
                last_taxpayer_failure["user_es"] = user_es
                last_taxpayer_failure["tech"] = tech_combined
                _update_job(
                    extraction_job_id,
                    payload=payload,
                    failure_phase=last_taxpayer_failure["phase"],
                    failure_message_user=user_es,
                    failure_message_technical=tech_combined,
                )

        def on_phase(taxpayer: Taxpayer, phase: ExtractionPhase, message: str) -> None:
            _update_phase_state(
                extraction_job_id,
                payload,
                taxpayer_id=taxpayer.id,
                phase=phase,
                message=message,
            )

        try:
            result = LpgPlaywrightPipelineService().run(
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                taxpayer_ids=taxpayer_ids,
                headless=True,
                timeout_ms=timeout_ms,
                type_delay_ms=type_delay_ms,
                slow_mo_ms=slow_mo_ms,
                post_action_delay_ms=post_action_delay_ms,
                login_max_retries=login_max_retries,
                humanize_delays=humanize_delays,
                retry_max_attempts=retry_max_attempts,
                retry_base_delay_ms=retry_base_delay_ms,
                on_taxpayer_start=on_taxpayer_start,
                on_taxpayer_finish=on_taxpayer_finish,
                on_phase=on_phase,
            )
            final_payload = result.to_dict()
            # Preserve per-client progress block so the UI can still show per-taxpayer phase/failure
            final_payload["progress"] = payload.get("progress")

            status = "completed"
            error_message = None
            job_failure_user: str | None = None
            job_failure_tech: str | None = None
            job_failure_phase: str | None = None
            if result.taxpayers_total > 0 and result.taxpayers_ok == 0 and result.taxpayers_error > 0:
                status = "failed"
                error_message = (
                    "No se pudo procesar ningún cliente. "
                    "Revisá logs del worker para detalle técnico."
                )
                job_failure_user = last_taxpayer_failure["user_es"]
                job_failure_tech = last_taxpayer_failure["tech"]
                job_failure_phase = last_taxpayer_failure["phase"]

            _update_job(
                extraction_job_id,
                status=status,
                result=final_payload,
                finished_at=now_cordoba_naive(),
                error_message=error_message,
                failure_phase=job_failure_phase,
                failure_message_user=job_failure_user,
                failure_message_technical=job_failure_tech,
            )
            logger.info(
                "JOB_FINISHED | job_id=%s status=%s taxpayers_total=%s taxpayers_ok=%s taxpayers_error=%s",
                extraction_job_id,
                status,
                result.taxpayers_total,
                result.taxpayers_ok,
                result.taxpayers_error,
            )
        except Exception as exc:
            db.session.rollback()
            user_es, tech_en = map_failure(None, "unknown", False)
            tech_combined = _truncate(f"{tech_en} | {exc}")
            _update_job(
                extraction_job_id,
                status="failed",
                finished_at=now_cordoba_naive(),
                error_message=str(exc),
                failure_phase=None,
                failure_message_user=user_es,
                failure_message_technical=tech_combined,
            )
            logger.exception("JOB_FAILED | job_id=%s error=%s", extraction_job_id, exc)
