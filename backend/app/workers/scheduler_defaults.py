"""Defaults para encolar jobs Playwright desde flujos automatizados
(scheduler tick, scheduler run-now). Los endpoints manuales tienen su propio
parseo (`backend/app/api/playwright.py::_parse_and_validate_run_payload`);
estos constantes son para flujos que no reciben payload del usuario.

Las fechas se calculan en runtime (no son constantes a nivel de módulo) para
que cada job encolado use la fecha del momento en que se dispara, no la fecha
en que arrancó el worker. El worker de Playwright NO sabe derivar defaults a
partir de None — los inputs DD/MM/YYYY se llenan directamente en los campos
de búsqueda del portal ARCA — así que generamos strings concretos acá.

Decisión: Opción 2 del plan v2 (computar fechas localmente como
`DD/MM/YYYY`), porque el pipeline de Playwright requiere strings concretos y
cambiar la firma del worker para aceptar `None` también requeriría tocar
`lpg_playwright_pipeline.py` y `lpg_consulta_client.py`. Opción 2 mantiene el
cambio acotado al scheduler.
"""
from __future__ import annotations

from datetime import timedelta

from ..time_utils import now_cordoba_naive

DEFAULT_VENTANA_DIAS = 90
DEFAULT_TIMEOUT_MS = 30000
DEFAULT_NAV_LOGIN_TIMEOUT_MS = 60000
DEFAULT_TYPE_DELAY_MS = 80
DEFAULT_SLOW_MO_MS = 0
DEFAULT_POST_ACTION_DELAY_MS = 0
DEFAULT_LOGIN_MAX_RETRIES = 2
DEFAULT_HUMANIZE_DELAYS = True
DEFAULT_RETRY_MAX_ATTEMPTS = 2
DEFAULT_RETRY_BASE_DELAY_MS = 1000


def _default_fechas(dias_extraccion: int = DEFAULT_VENTANA_DIAS) -> tuple[str, str]:
    """Devuelve `(fecha_desde, fecha_hasta)` en formato DD/MM/YYYY.

    Ventana: últimos `dias_extraccion` días hasta hoy (zona Córdoba).
    """
    hoy = now_cordoba_naive().date()
    desde = hoy - timedelta(days=dias_extraccion)
    fmt = "%d/%m/%Y"
    return desde.strftime(fmt), hoy.strftime(fmt)


def scheduler_enqueue_kwargs(
    taxpayer_id: int, dias_extraccion: int = DEFAULT_VENTANA_DIAS
) -> dict:
    """Kwargs completos para `queue.enqueue(run_playwright_pipeline_job, **)`.

    `dias_extraccion` controla la ventana temporal (hoy - N días → hoy). Default
    DEFAULT_VENTANA_DIAS (90) por compatibilidad — llamadores nuevos pasan el
    valor configurado por taxpayer.

    El `extraction_job_id` NO va acá — lo agrega el llamador después de
    persistir el `ExtractionJob`.
    """
    fecha_desde, fecha_hasta = _default_fechas(dias_extraccion)
    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "taxpayer_ids": [taxpayer_id],
        "timeout_ms": DEFAULT_TIMEOUT_MS,
        "nav_login_timeout_ms": DEFAULT_NAV_LOGIN_TIMEOUT_MS,
        "type_delay_ms": DEFAULT_TYPE_DELAY_MS,
        "slow_mo_ms": DEFAULT_SLOW_MO_MS,
        "post_action_delay_ms": DEFAULT_POST_ACTION_DELAY_MS,
        "login_max_retries": DEFAULT_LOGIN_MAX_RETRIES,
        "humanize_delays": DEFAULT_HUMANIZE_DELAYS,
        "retry_max_attempts": DEFAULT_RETRY_MAX_ATTEMPTS,
        "retry_base_delay_ms": DEFAULT_RETRY_BASE_DELAY_MS,
    }
