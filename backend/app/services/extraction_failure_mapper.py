from __future__ import annotations

from .extraction_phases import ExtractionPhase

_LOGIN_PHASES = {ExtractionPhase.LOGIN_START, ExtractionPhase.LOGIN_CONFIRMED}
_CONSULTA_PHASES = {
    ExtractionPhase.OPEN_CONSULTA_RECIBIDAS,
    ExtractionPhase.LISTING_COES,
}
_WS_PHASES = {ExtractionPhase.DOWNLOADING_COE, ExtractionPhase.SAVING_TO_WS}

_TRANSIENT_ERRORS = {"timeout", "network", "arca_unavailable"}
_ARCA_SLOW_ERRORS = {"timeout", "arca_unavailable"}
# If the dropdown click in SEARCH_SERVICE succeeded, any post-click failure
# points to ARCA latency, not missing service adhesion — so "unknown" also
# maps to ARCA_SLOW_AFTER_DROPDOWN here (but only here).
_SEARCH_SERVICE_AFTER_DROPDOWN_ERRORS = {"timeout", "arca_unavailable", "unknown"}
_SERVICE_NOT_ADHERED_ERRORS = {"timeout", "arca_unavailable", "unknown"}

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


def map_failure(
    phase: ExtractionPhase | None,
    error_type: str,
    dropdown_clicked: bool = False,
) -> tuple[str, str]:
    if phase in _LOGIN_PHASES:
        if error_type == "auth_failed":
            return (_AUTH_FAILED_USER_ES, "AUTH_FAILED at login")
        if error_type in _TRANSIENT_ERRORS:
            return (_TRANSIENT_LOGIN_USER_ES, "TRANSIENT_LOGIN")

    if phase == ExtractionPhase.SEARCH_SERVICE:
        if dropdown_clicked and error_type in _SEARCH_SERVICE_AFTER_DROPDOWN_ERRORS:
            return (
                _ARCA_SLOW_AFTER_DROPDOWN_USER_ES,
                "ARCA_SLOW_AFTER_DROPDOWN",
            )
        if not dropdown_clicked and error_type in _SERVICE_NOT_ADHERED_ERRORS:
            return (_SERVICE_NOT_ADHERED_USER_ES, "SERVICE_NOT_ADHERED")

    if phase == ExtractionPhase.OPEN_SERVICE and error_type in _ARCA_SLOW_ERRORS:
        return (_OPEN_SERVICE_TIMEOUT_USER_ES, "OPEN_SERVICE_TIMEOUT")

    if phase == ExtractionPhase.SELECT_EMPRESA:
        return (_EMPRESA_NOT_FOUND_USER_ES, "EMPRESA_NOT_FOUND")

    if phase in _CONSULTA_PHASES and error_type in _TRANSIENT_ERRORS:
        return (_CONSULTA_FAILURE_USER_ES, "CONSULTA_FAILURE")

    if phase in _WS_PHASES:
        return (_WS_COE_ERRORS_USER_ES, "WS_COE_ERRORS")

    if error_type == "network":
        return (_NETWORK_ERROR_USER_ES, "NETWORK_ERROR")

    return (_UNKNOWN_ERROR_USER_ES, "UNKNOWN_ERROR")


def _truncate(text: str, limit: int = 1000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
