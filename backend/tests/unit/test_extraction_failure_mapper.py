from __future__ import annotations

import pytest

from app.services.extraction_failure_mapper import (
    _truncate,
    map_failure,
)
from app.services.extraction_phases import ExtractionPhase

_AUTH_FAILED_USER_ES = (
    "La clave fiscal del cliente es incorrecta o está vencida. "
    "Actualizala en el detalle del cliente."
)
_TRANSIENT_LOGIN_USER_ES = (
    "ARCA está respondiendo lento durante el login. Reintentá en unos minutos."
)
_ARCA_SLOW_AFTER_DROPDOWN_USER_ES = (
    "ARCA está respondiendo lento, reintentá en unos minutos."
)
_SERVICE_NOT_ADHERED_USER_ES = (
    "Verificá que el servicio 'Liquidación primaria de granos' esté adherido "
    "en ARCA para este cliente."
)
_OPEN_SERVICE_TIMEOUT_USER_ES = (
    "ARCA tardó en abrir el servicio. Reintentá en unos minutos."
)
_EMPRESA_NOT_FOUND_USER_ES = (
    "No aparece el CUIT representado como empresa disponible. "
    "Revisá la adhesión en ARCA."
)
_CONSULTA_FAILURE_USER_ES = "ARCA falló al consultar liquidaciones. Reintentá."
_WS_COE_ERRORS_USER_ES = (
    "Hubo errores procesando algunos COEs. Revisá el detalle por cliente."
)
_NETWORK_ERROR_USER_ES = (
    "Sin conexión con ARCA. Verificá la red e intentá de nuevo."
)
_UNKNOWN_ERROR_USER_ES = (
    "No pudimos completar la extracción. Reintentá; si persiste, contactá soporte."
)


# ---------------------------------------------------------------------------
# Login phases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phase",
    [ExtractionPhase.LOGIN_START, ExtractionPhase.LOGIN_CONFIRMED],
    ids=["LOGIN_START", "LOGIN_CONFIRMED"],
)
def test_login_phase_auth_failed_returns_auth_failed_user_es(phase: ExtractionPhase) -> None:
    user_es, tech_en = map_failure(phase, "auth_failed", False)
    assert user_es == _AUTH_FAILED_USER_ES
    assert tech_en == "AUTH_FAILED at login"


@pytest.mark.parametrize(
    "phase",
    [ExtractionPhase.LOGIN_START, ExtractionPhase.LOGIN_CONFIRMED],
    ids=["LOGIN_START", "LOGIN_CONFIRMED"],
)
@pytest.mark.parametrize(
    "error_type",
    ["timeout", "network", "arca_unavailable"],
    ids=["timeout", "network", "arca_unavailable"],
)
def test_login_phase_transient_returns_transient_login(
    phase: ExtractionPhase, error_type: str
) -> None:
    user_es, tech_en = map_failure(phase, error_type, False)
    assert user_es == _TRANSIENT_LOGIN_USER_ES
    assert tech_en == "TRANSIENT_LOGIN"


# ---------------------------------------------------------------------------
# SEARCH_SERVICE phase
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "error_type",
    ["timeout", "arca_unavailable"],
    ids=["timeout", "arca_unavailable"],
)
def test_search_service_dropdown_clicked_returns_arca_slow(error_type: str) -> None:
    user_es, tech_en = map_failure(ExtractionPhase.SEARCH_SERVICE, error_type, True)
    assert user_es == _ARCA_SLOW_AFTER_DROPDOWN_USER_ES
    assert tech_en == "ARCA_SLOW_AFTER_DROPDOWN"


@pytest.mark.parametrize(
    "error_type",
    ["timeout", "arca_unavailable", "unknown"],
    ids=["timeout", "arca_unavailable", "unknown"],
)
def test_search_service_no_dropdown_returns_service_not_adhered(error_type: str) -> None:
    user_es, tech_en = map_failure(ExtractionPhase.SEARCH_SERVICE, error_type, False)
    assert user_es == _SERVICE_NOT_ADHERED_USER_ES
    assert tech_en == "SERVICE_NOT_ADHERED"


def test_search_service_network_no_dropdown_falls_through_to_network() -> None:
    # error_type=network is NOT in _SERVICE_NOT_ADHERED_ERRORS, so it falls
    # through to the generic network rule.
    user_es, tech_en = map_failure(ExtractionPhase.SEARCH_SERVICE, "network", False)
    assert user_es == _NETWORK_ERROR_USER_ES
    assert tech_en == "NETWORK_ERROR"


# ---------------------------------------------------------------------------
# OPEN_SERVICE phase
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "error_type",
    ["timeout", "arca_unavailable"],
    ids=["timeout", "arca_unavailable"],
)
def test_open_service_arca_slow_errors_returns_open_service_timeout(
    error_type: str,
) -> None:
    user_es, tech_en = map_failure(ExtractionPhase.OPEN_SERVICE, error_type, False)
    assert user_es == _OPEN_SERVICE_TIMEOUT_USER_ES
    assert tech_en == "OPEN_SERVICE_TIMEOUT"


# ---------------------------------------------------------------------------
# SELECT_EMPRESA phase
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "error_type",
    ["timeout", "network", "arca_unavailable", "auth_failed", "unknown"],
    ids=["timeout", "network", "arca_unavailable", "auth_failed", "unknown"],
)
@pytest.mark.parametrize(
    "dropdown_clicked", [True, False], ids=["dropdown=T", "dropdown=F"]
)
def test_select_empresa_any_error_returns_empresa_not_found(
    error_type: str, dropdown_clicked: bool
) -> None:
    user_es, tech_en = map_failure(
        ExtractionPhase.SELECT_EMPRESA, error_type, dropdown_clicked
    )
    assert user_es == _EMPRESA_NOT_FOUND_USER_ES
    assert tech_en == "EMPRESA_NOT_FOUND"


# ---------------------------------------------------------------------------
# Consulta phases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phase",
    [ExtractionPhase.OPEN_CONSULTA_RECIBIDAS, ExtractionPhase.LISTING_COES],
    ids=["OPEN_CONSULTA_RECIBIDAS", "LISTING_COES"],
)
@pytest.mark.parametrize(
    "error_type",
    ["timeout", "network", "arca_unavailable"],
    ids=["timeout", "network", "arca_unavailable"],
)
def test_consulta_phases_transient_returns_consulta_failure(
    phase: ExtractionPhase, error_type: str
) -> None:
    user_es, tech_en = map_failure(phase, error_type, False)
    assert user_es == _CONSULTA_FAILURE_USER_ES
    assert tech_en == "CONSULTA_FAILURE"


# ---------------------------------------------------------------------------
# WS phases (DOWNLOADING_COE, SAVING_TO_WS)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phase",
    [ExtractionPhase.DOWNLOADING_COE, ExtractionPhase.SAVING_TO_WS],
    ids=["DOWNLOADING_COE", "SAVING_TO_WS"],
)
@pytest.mark.parametrize(
    "error_type",
    ["timeout", "network", "arca_unavailable", "auth_failed", "unknown"],
    ids=["timeout", "network", "arca_unavailable", "auth_failed", "unknown"],
)
def test_ws_phases_any_error_returns_ws_coe_errors(
    phase: ExtractionPhase, error_type: str
) -> None:
    user_es, tech_en = map_failure(phase, error_type, False)
    assert user_es == _WS_COE_ERRORS_USER_ES
    assert tech_en == "WS_COE_ERRORS"


# ---------------------------------------------------------------------------
# Generic network fallthrough (any phase not handled earlier)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phase",
    [
        None,
        ExtractionPhase.LAUNCHING_BROWSER,
        ExtractionPhase.OPEN_SERVICE,
        ExtractionPhase.FINISHED,
    ],
    ids=["None", "LAUNCHING_BROWSER", "OPEN_SERVICE", "FINISHED"],
)
def test_network_error_falls_through_to_network_error(
    phase: ExtractionPhase | None,
) -> None:
    user_es, tech_en = map_failure(phase, "network", False)
    assert user_es == _NETWORK_ERROR_USER_ES
    assert tech_en == "NETWORK_ERROR"


# ---------------------------------------------------------------------------
# Unknown / default fallback
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phase",
    [
        None,
        ExtractionPhase.LAUNCHING_BROWSER,
        ExtractionPhase.FINISHED,
    ],
    ids=["None", "LAUNCHING_BROWSER", "FINISHED"],
)
@pytest.mark.parametrize(
    "error_type",
    ["unknown", "auth_failed", "timeout", "arca_unavailable"],
    ids=["unknown", "auth_failed", "timeout", "arca_unavailable"],
)
def test_unhandled_combinations_fall_back_to_unknown_error(
    phase: ExtractionPhase | None, error_type: str
) -> None:
    user_es, tech_en = map_failure(phase, error_type, False)
    assert user_es == _UNKNOWN_ERROR_USER_ES
    assert tech_en == "UNKNOWN_ERROR"


# ---------------------------------------------------------------------------
# Default invariant: always returns non-empty tuple of two strings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phase",
    [None, *list(ExtractionPhase)],
    ids=["None", *[p.value for p in ExtractionPhase]],
)
@pytest.mark.parametrize(
    "error_type",
    ["network", "timeout", "arca_unavailable", "auth_failed", "unknown"],
    ids=["network", "timeout", "arca_unavailable", "auth_failed", "unknown"],
)
@pytest.mark.parametrize(
    "dropdown_clicked", [True, False], ids=["dropdown=T", "dropdown=F"]
)
def test_mapper_never_returns_empty_or_none(
    phase: ExtractionPhase | None, error_type: str, dropdown_clicked: bool
) -> None:
    result = map_failure(phase, error_type, dropdown_clicked)
    assert isinstance(result, tuple)
    assert len(result) == 2
    user_es, tech_en = result
    assert isinstance(user_es, str) and user_es != ""
    assert isinstance(tech_en, str) and tech_en != ""


# ---------------------------------------------------------------------------
# _truncate helper
# ---------------------------------------------------------------------------

def test_truncate_short_text_unchanged() -> None:
    assert _truncate("hello") == "hello"


def test_truncate_text_exactly_at_default_limit_unchanged() -> None:
    text = "x" * 1000
    assert _truncate(text) == text


def test_truncate_text_longer_than_default_limit_truncates_with_ellipsis() -> None:
    text = "x" * 1500
    result = _truncate(text)
    assert result == ("x" * 1000) + "..."
    assert len(result) == 1003


def test_truncate_with_custom_limit_short_text_unchanged() -> None:
    assert _truncate("hello", 10) == "hello"


def test_truncate_with_custom_limit_text_at_limit_unchanged() -> None:
    assert _truncate("abcde", 5) == "abcde"


def test_truncate_with_custom_limit_text_above_limit_truncates() -> None:
    assert _truncate("abcdefghij", 5) == "abcde..."


def test_truncate_default_limit_is_1000() -> None:
    # One char above the default must trigger truncation.
    text = "x" * 1001
    result = _truncate(text)
    assert result.endswith("...")
    assert len(result) == 1003
