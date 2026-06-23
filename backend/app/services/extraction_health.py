from __future__ import annotations

from ..extensions import db
from ..models import Taxpayer, ExtractionJob
from ..time_utils import now_cordoba_naive

ACTIONABLE_CODES: set[str] = {"AUTH_FAILED", "SERVICE_NOT_ADHERED", "EMPRESA_NOT_FOUND"}
RED_THRESHOLD_DAYS: int = 3

_ESTADO_ORDER = {"rojo": 0, "amarillo": 1, "gris": 2, "verde": 3}


def classify(
    last_status: str | None,
    failure_code: str | None,
    dias_sin_exito: int | None,
) -> tuple[str, bool]:
    """Clasifica el estado de salud de un cliente.

    - verde: último job completed y reciente.
    - rojo: último fallo con causa accionable (AUTH_FAILED / SERVICE_NOT_ADHERED /
      EMPRESA_NOT_FOUND), o causa transitoria que ya lleva >= RED_THRESHOLD_DAYS.
    - amarillo: último fallo con causa transitoria conocida y < RED_THRESHOLD_DAYS.
    - gris: sin jobs, o último fallo sin código (job viejo / causa desconocida).
    """
    if last_status == "completed":
        return ("verde", False)
    if last_status in ("failed", "partial"):
        if failure_code in ACTIONABLE_CODES:
            return ("rojo", True)
        if failure_code is None:
            return ("gris", False)
        # Transitorio conocido.
        if dias_sin_exito is not None and dias_sin_exito >= RED_THRESHOLD_DAYS:
            return ("rojo", False)
        return ("amarillo", False)
    return ("gris", False)


def _dias_sin_exito(ultima_ok) -> int | None:
    if ultima_ok is None:
        return None
    hoy = now_cordoba_naive().date()
    return (hoy - ultima_ok.date()).days


def compute_health() -> dict:
    taxpayers = (
        Taxpayer.query.filter(Taxpayer.activo == True)  # noqa: E712
        .order_by(Taxpayer.id)
        .all()
    )
    clientes: list[dict] = []
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0, "gris": 0}

    for t in taxpayers:
        last_job = (
            ExtractionJob.query.filter(ExtractionJob.taxpayer_id == t.id)
            .order_by(ExtractionJob.created_at.desc())
            .first()
        )
        ultima_ok_job = (
            ExtractionJob.query.filter(
                ExtractionJob.taxpayer_id == t.id,
                ExtractionJob.status == "completed",
                ExtractionJob.finished_at.isnot(None),
            )
            .order_by(ExtractionJob.finished_at.desc())
            .first()
        )
        ultima_ok = ultima_ok_job.finished_at if ultima_ok_job else None
        dias = _dias_sin_exito(ultima_ok)

        last_status = last_job.status if last_job else None
        failure_code = last_job.failure_code if last_job else None
        estado, accionable = classify(last_status, failure_code, dias)

        es_fallo = last_status in ("failed", "partial")
        clientes.append(
            {
                "taxpayer_id": t.id,
                "empresa": t.empresa,
                "estado": estado,
                "dias_sin_exito": dias,
                "ultima_ok": ultima_ok.date().isoformat() if ultima_ok else None,
                "causa_codigo": failure_code if es_fallo else None,
                "causa_mensaje": (last_job.failure_message_user if es_fallo else None),
                "es_accionable": accionable,
            }
        )
        resumen[estado] += 1

    clientes.sort(
        key=lambda c: (
            _ESTADO_ORDER[c["estado"]],
            -(c["dias_sin_exito"] or 0),
        )
    )

    return {
        "generado_en": now_cordoba_naive().isoformat(),
        "resumen": resumen,
        "clientes": clientes,
    }
