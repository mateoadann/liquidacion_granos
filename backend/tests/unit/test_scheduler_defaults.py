"""Tests para app.workers.scheduler_defaults.

Verifican que `scheduler_enqueue_kwargs()` devuelve un dict completo con
todos los kwargs requeridos por `run_playwright_pipeline_job` (excepto
`extraction_job_id`, que se agrega en el llamador).
"""
from __future__ import annotations

import json
import re
from datetime import date

from app.workers.scheduler_defaults import (
    DEFAULT_VENTANA_DIAS,
    scheduler_enqueue_kwargs,
)

DATE_REGEX = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def test_scheduler_enqueue_kwargs_incluye_todos_los_requeridos():
    """`run_playwright_pipeline_job` exige estos kwargs sí o sí; el dict
    devuelto debe cubrirlos todos (extraction_job_id lo agrega el llamador).
    """
    requeridos = {
        "fecha_desde",
        "fecha_hasta",
        "taxpayer_ids",
        "timeout_ms",
        "nav_login_timeout_ms",
        "type_delay_ms",
        "slow_mo_ms",
        "post_action_delay_ms",
        "login_max_retries",
        "humanize_delays",
        "retry_max_attempts",
        "retry_base_delay_ms",
    }
    kwargs = scheduler_enqueue_kwargs(taxpayer_id=42)
    assert set(kwargs.keys()) == requeridos
    # Tipos basicos
    assert isinstance(kwargs["timeout_ms"], int)
    assert isinstance(kwargs["type_delay_ms"], int)
    assert isinstance(kwargs["humanize_delays"], bool)
    # Las fechas son strings DD/MM/YYYY (formato esperado por el portal ARCA)
    assert isinstance(kwargs["fecha_desde"], str)
    assert isinstance(kwargs["fecha_hasta"], str)
    assert DATE_REGEX.match(kwargs["fecha_desde"])
    assert DATE_REGEX.match(kwargs["fecha_hasta"])


def test_scheduler_enqueue_kwargs_taxpayer_id_en_lista():
    """El taxpayer_id pasado debe envolverse en una lista de 1 elemento
    para que el worker matchee la firma `taxpayer_ids: list[int] | None`.
    """
    kwargs = scheduler_enqueue_kwargs(taxpayer_id=7)
    assert kwargs["taxpayer_ids"] == [7]


def test_scheduler_enqueue_kwargs_devuelve_dict_serializable():
    """El dict debe ser JSON-serializable: sin objetos exoticos, porque el
    worker puede loguearlo y queremos evitar sorpresas de serializacion.
    """
    kwargs = scheduler_enqueue_kwargs(taxpayer_id=123)
    blob = json.dumps(kwargs)
    assert blob


def test_scheduler_enqueue_kwargs_ventana_de_90_dias():
    """fecha_desde debe ser ~90 dias antes de fecha_hasta."""
    kwargs = scheduler_enqueue_kwargs(taxpayer_id=1)
    fmt = "%d/%m/%Y"
    from datetime import datetime

    desde = datetime.strptime(kwargs["fecha_desde"], fmt).date()
    hasta = datetime.strptime(kwargs["fecha_hasta"], fmt).date()
    assert (hasta - desde).days == DEFAULT_VENTANA_DIAS


def test_scheduler_enqueue_kwargs_fecha_hasta_es_hoy_local():
    """fecha_hasta deberia ser hoy (zona Cordoba). Aceptamos hoy +/- 1 dia
    para evitar flake si el test corre justo en cambio de dia.
    """
    kwargs = scheduler_enqueue_kwargs(taxpayer_id=1)
    from datetime import datetime

    hasta = datetime.strptime(kwargs["fecha_hasta"], "%d/%m/%Y").date()
    hoy = date.today()
    assert abs((hasta - hoy).days) <= 1


def test_scheduler_enqueue_kwargs_usa_dias_extraccion_param():
    """El parámetro `dias_extraccion` debe controlar la ventana fecha_desde."""
    from datetime import datetime

    kwargs = scheduler_enqueue_kwargs(taxpayer_id=1, dias_extraccion=30)
    fmt = "%d/%m/%Y"
    desde = datetime.strptime(kwargs["fecha_desde"], fmt).date()
    hasta = datetime.strptime(kwargs["fecha_hasta"], fmt).date()
    assert (hasta - desde).days == 30


def test_scheduler_enqueue_kwargs_default_90_si_no_se_pasa():
    """Sin pasar dias_extraccion, ventana debe ser 90 días (compatibilidad)."""
    from datetime import datetime

    kwargs = scheduler_enqueue_kwargs(taxpayer_id=1)
    fmt = "%d/%m/%Y"
    desde = datetime.strptime(kwargs["fecha_desde"], fmt).date()
    hasta = datetime.strptime(kwargs["fecha_hasta"], fmt).date()
    assert (hasta - desde).days == 90


def test_scheduler_enqueue_kwargs_fecha_desde_es_hoy_menos_dias():
    """fecha_desde debe ser exactamente hoy - dias_extraccion (zona Cordoba)."""
    from datetime import datetime, timedelta

    kwargs = scheduler_enqueue_kwargs(taxpayer_id=1, dias_extraccion=10)
    fmt = "%d/%m/%Y"
    desde = datetime.strptime(kwargs["fecha_desde"], fmt).date()
    hoy = date.today()
    esperado = hoy - timedelta(days=10)
    # +/- 1 día para flake en cambio de día (zona Córdoba vs UTC).
    assert abs((desde - esperado).days) <= 1
