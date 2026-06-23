from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..extensions import db
from ..integrations.arca import ArcaWslpgClient
from ..integrations.arca.client import ArcaDiscoveryConfig
from ..integrations.playwright import (
    ArcaLpgPlaywrightClient,
    LpgConsultaRequest,
    LpgCredentials,
    PhaseCallback,
    PlaywrightFlowError,
)
from ..models import LpgDocument, Taxpayer
from .certificate_validator import (
    CertificateValidationError,
    validate_certificate_and_key_paths,
)
from .crypto_service import decrypt_secret, is_placeholder_secret
from .datos_limpios_builder import DatosLimpiosBuilder
from .extraction_phases import PHASE_MESSAGES_ES, ExtractionPhase
from .lpg_document_utils import (
    build_ws_client_for_taxpayer,
    coe_already_exists,
    save_lpg_document_from_ws,
    validate_taxpayer_ws_config,
)
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TaxpayerPipelineResult:
    taxpayer_id: int
    empresa: str
    cuit: str
    cuit_representado: str
    outcome: str = "done"  # "done" | "partial" | "error"
    error: str | None = None
    total_rows: int = 0
    total_coes_detectados: int = 0
    total_coes_nuevos: int = 0
    total_omitidos_existentes: int = 0
    total_procesados_ok: int = 0
    total_procesados_error: int = 0
    coes_nuevos: list[str] = field(default_factory=list)
    coes_error: list[dict[str, str]] = field(default_factory=list)
    consulta: dict[str, Any] | None = None
    # Failure metadata for the failure mapper (populated on outcome != "done")
    failure_phase: ExtractionPhase | None = None
    failure_error_type: str | None = None
    failure_dropdown_clicked: bool = False
    # Which path opened the LPG service for this run: "search_box" | "direct_url".
    # None means the extraction failed before reaching the service-open step.
    service_open_method: str | None = None


def _taxpayer_result_to_dict(item: TaxpayerPipelineResult) -> dict[str, Any]:
    data = asdict(item)
    # Backward-compat: frontend (PlaywrightTaxpayerRunResult) still consumes "ok"
    # as a boolean for legacy result rendering. Derive it from outcome.
    data["ok"] = item.outcome == "done"
    return data


@dataclass(slots=True)
class PipelineRunResult:
    started_at: str
    finished_at: str
    fecha_desde: str
    fecha_hasta: str
    taxpayers_total: int
    taxpayers_ok: int
    taxpayers_partial: int
    taxpayers_error: int
    results: list[TaxpayerPipelineResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "fecha_desde": self.fecha_desde,
            "fecha_hasta": self.fecha_hasta,
            "taxpayers_total": self.taxpayers_total,
            "taxpayers_ok": self.taxpayers_ok,
            "taxpayers_partial": self.taxpayers_partial,
            "taxpayers_error": self.taxpayers_error,
            "results": [_taxpayer_result_to_dict(item) for item in self.results],
        }


class LpgPlaywrightPipelineService:
    def run(
        self,
        *,
        fecha_desde: str,
        fecha_hasta: str,
        taxpayer_ids: list[int] | None = None,
        headless: bool = True,
        timeout_ms: int = 30_000,
        nav_login_timeout_ms: int = 60_000,
        type_delay_ms: int = 80,
        slow_mo_ms: int = 0,
        post_action_delay_ms: int = 0,
        login_max_retries: int = 2,
        humanize_delays: bool = True,
        retry_max_attempts: int = 2,
        retry_base_delay_ms: int = 1000,
        on_taxpayer_start: Callable[[Taxpayer], None] | None = None,
        on_taxpayer_finish: Callable[[TaxpayerPipelineResult], None] | None = None,
        on_phase: Callable[[Taxpayer, ExtractionPhase, str], None] | None = None,
    ) -> PipelineRunResult:
        started = now_cordoba_naive()
        logger.info(
            "Playwright pipeline start | desde=%s hasta=%s taxpayers=%s headless=%s timeout_ms=%s type_delay_ms=%s",
            fecha_desde,
            fecha_hasta,
            taxpayer_ids or "todos",
            headless,
            timeout_ms,
            type_delay_ms,
        )

        query = Taxpayer.query.filter(
            Taxpayer.activo.is_(True), Taxpayer.playwright_enabled.is_(True)
        ).order_by(Taxpayer.id.asc())
        if taxpayer_ids:
            query = query.filter(Taxpayer.id.in_(taxpayer_ids))
        taxpayers = query.all()

        results: list[TaxpayerPipelineResult] = []
        for taxpayer in taxpayers:
            if on_taxpayer_start:
                on_taxpayer_start(taxpayer)
            taxpayer_phase_cb: PhaseCallback | None
            if on_phase is None:
                taxpayer_phase_cb = None
            else:
                outer_on_phase = on_phase
                tp_ref = taxpayer

                def taxpayer_phase_cb(
                    phase: ExtractionPhase,
                    message: str,
                    _tp: Taxpayer = tp_ref,
                    _cb: Callable[[Taxpayer, ExtractionPhase, str], None] = outer_on_phase,
                ) -> None:
                    _cb(_tp, phase, message)
            result = self._process_taxpayer(
                taxpayer=taxpayer,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                headless=headless,
                timeout_ms=timeout_ms,
                nav_login_timeout_ms=nav_login_timeout_ms,
                type_delay_ms=type_delay_ms,
                slow_mo_ms=slow_mo_ms,
                post_action_delay_ms=post_action_delay_ms,
                login_max_retries=login_max_retries,
                humanize_delays=humanize_delays,
                retry_max_attempts=retry_max_attempts,
                retry_base_delay_ms=retry_base_delay_ms,
                on_phase=taxpayer_phase_cb,
            )
            results.append(result)
            if on_taxpayer_finish:
                on_taxpayer_finish(result)
            logger.info(
                "Playwright pipeline taxpayer result | id=%s empresa=%s outcome=%s detectados=%s nuevos=%s omitidos=%s ok_ws=%s error_ws=%s error=%s",
                result.taxpayer_id,
                result.empresa,
                result.outcome,
                result.total_coes_detectados,
                result.total_coes_nuevos,
                result.total_omitidos_existentes,
                result.total_procesados_ok,
                result.total_procesados_error,
                result.error,
            )

        finished = now_cordoba_naive()
        taxpayers_ok = sum(1 for item in results if item.outcome == "done")
        taxpayers_partial = sum(1 for item in results if item.outcome == "partial")
        taxpayers_error = sum(1 for item in results if item.outcome == "error")
        return PipelineRunResult(
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            taxpayers_total=len(results),
            taxpayers_ok=taxpayers_ok,
            taxpayers_partial=taxpayers_partial,
            taxpayers_error=taxpayers_error,
            results=results,
        )

    def _process_taxpayer(
        self,
        *,
        taxpayer: Taxpayer,
        fecha_desde: str,
        fecha_hasta: str,
        headless: bool,
        timeout_ms: int,
        nav_login_timeout_ms: int = 60_000,
        type_delay_ms: int,
        slow_mo_ms: int,
        post_action_delay_ms: int,
        login_max_retries: int,
        humanize_delays: bool,
        retry_max_attempts: int,
        retry_base_delay_ms: int,
        on_phase: PhaseCallback | None = None,
    ) -> TaxpayerPipelineResult:
        logger.info(
            "Taxpayer start | id=%s empresa=%s cuit=%s cuit_representado=%s",
            taxpayer.id,
            taxpayer.empresa,
            taxpayer.cuit,
            taxpayer.cuit_representado,
        )
        base = TaxpayerPipelineResult(
            taxpayer_id=taxpayer.id,
            empresa=taxpayer.empresa,
            cuit=taxpayer.cuit,
            cuit_representado=taxpayer.cuit_representado,
            outcome="error",
        )

        try:
            logger.info(
                "CLIENT_CONFIG_VALIDATE_START | taxpayer_id=%s empresa=%s",
                taxpayer.id,
                taxpayer.empresa,
            )
            clave = self._resolve_clave_fiscal(taxpayer)
            self._validate_taxpayer_ws_config(taxpayer)
            logger.info(
                "CLIENT_CONFIG_VALIDATE_OK | taxpayer_id=%s empresa=%s",
                taxpayer.id,
                taxpayer.empresa,
            )
        except ValueError as exc:
            base.error = str(exc)
            logger.warning(
                "CLIENT_CONFIG_VALIDATE_ERROR | taxpayer_id=%s empresa=%s error=%s",
                taxpayer.id,
                taxpayer.empresa,
                base.error,
            )
            return base

        client = ArcaLpgPlaywrightClient()
        try:
            logger.info(
                "CLIENT_PLAYWRIGHT_START | taxpayer_id=%s empresa=%s",
                taxpayer.id,
                taxpayer.empresa,
            )
            consulta = client.run(
                LpgConsultaRequest(
                    credentials=LpgCredentials(cuit=taxpayer.cuit, clave_fiscal=clave),
                    empresa=taxpayer.empresa,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    headless=headless,
                    timeout_ms=timeout_ms,
                    nav_login_timeout_ms=nav_login_timeout_ms,
                    type_delay_ms=type_delay_ms,
                    slow_mo_ms=slow_mo_ms,
                    post_action_delay_ms=post_action_delay_ms,
                    login_max_retries=login_max_retries,
                    humanize_delays=humanize_delays,
                    retry_max_attempts=retry_max_attempts,
                    retry_base_delay_ms=retry_base_delay_ms,
                    on_phase=on_phase,
                )
            )
            logger.info(
                "CLIENT_PLAYWRIGHT_FINISHED | taxpayer_id=%s empresa=%s total_rows=%s total_coes=%s",
                taxpayer.id,
                taxpayer.empresa,
                consulta.total_rows,
                consulta.total_coes,
            )
        except PlaywrightFlowError as exc:
            base.error = f"Playwright: {exc}"
            # Prefer the explicit phase on the exception; fall back to the last
            # emitted phase tracked by the client (covers cases where the
            # exception was raised without a phase attribute).
            base.failure_phase = exc.phase if exc.phase is not None else client._current_phase
            base.failure_dropdown_clicked = exc.dropdown_clicked
            base.failure_error_type = client._classify_error(exc).error_type
            logger.error(
                "Taxpayer playwright error | id=%s empresa=%s error=%s phase=%s error_type=%s",
                taxpayer.id,
                taxpayer.empresa,
                base.error,
                base.failure_phase.value if base.failure_phase else None,
                base.failure_error_type,
            )
            return base
        except Exception as exc:
            base.error = f"Playwright inesperado: {exc}"
            # Use the last phase the client emitted as the best available
            # diagnostic when the exception is not a PlaywrightFlowError
            # (e.g. raw PlaywrightTimeoutError from an unwrapped step).
            base.failure_phase = client._current_phase
            base.failure_dropdown_clicked = client._search_dropdown_clicked
            base.failure_error_type = client._classify_error(exc).error_type
            logger.exception(
                "Taxpayer playwright unexpected error | id=%s empresa=%s phase=%s",
                taxpayer.id,
                taxpayer.empresa,
                base.failure_phase.value if base.failure_phase else None,
            )
            return base

        base.consulta = consulta.to_dict()
        base.total_rows = consulta.total_rows
        base.total_coes_detectados = consulta.total_coes
        base.service_open_method = client._service_open_method

        ws_client = self._build_ws_client_for_taxpayer(taxpayer)
        logger.info(
            "CLIENT_COE_PROCESSING_START | taxpayer_id=%s empresa=%s total_coes=%s",
            taxpayer.id,
            taxpayer.empresa,
            len(consulta.coes),
        )
        last_emitted_phase: ExtractionPhase | None = None

        def emit_ws_phase(phase: ExtractionPhase) -> None:
            nonlocal last_emitted_phase
            if on_phase is None or phase == last_emitted_phase:
                return
            try:
                on_phase(phase, PHASE_MESSAGES_ES[phase])
            except Exception:
                logger.exception("PIPELINE_ON_PHASE_CALLBACK_ERROR | phase=%s", phase.value)
            last_emitted_phase = phase

        for entry in consulta.coes:
            coe = entry.get("coe", "") if isinstance(entry, dict) else str(entry)
            tipo_operacion = entry.get("tipo_operacion", "") if isinstance(entry, dict) else ""
            is_ajuste_html = "ajuste" in tipo_operacion.casefold()

            if self._coe_exists(taxpayer.id, coe):
                base.total_omitidos_existentes += 1
                logger.info(
                    "COE_SKIP_EXISTS | taxpayer_id=%s empresa=%s coe=%s",
                    taxpayer.id,
                    taxpayer.empresa,
                    coe,
                )
                continue

            base.total_coes_nuevos += 1
            base.coes_nuevos.append(coe)
            logger.info(
                "COE_PROCESS_START | taxpayer_id=%s empresa=%s coe=%s tipo_op=%s",
                taxpayer.id,
                taxpayer.empresa,
                coe,
                tipo_operacion,
            )
            tipo_doc = "LPG"
            try:
                emit_ws_phase(ExtractionPhase.DOWNLOADING_COE)
                if is_ajuste_html:
                    logger.info(
                        "COE_DETECTED_AS_AJUSTE_FROM_HTML | taxpayer_id=%s coe=%s tipo_op=%s",
                        taxpayer.id, coe, tipo_operacion,
                    )
                    ws_result = ws_client.call_ajuste_x_coe(int(coe), pdf="N")
                    tipo_doc = "AJUSTE"
                else:
                    ws_result = ws_client.call_liquidacion_x_coe(int(coe), pdf="N")
                    if self._is_ajuste_error(ws_result):
                        logger.info(
                            "COE_IS_AJUSTE | taxpayer_id=%s coe=%s retrying with ajusteXCoeConsultar (error 1861)",
                            taxpayer.id, coe,
                        )
                        ws_result = ws_client.call_ajuste_x_coe(int(coe), pdf="N")
                        tipo_doc = "AJUSTE"
                emit_ws_phase(ExtractionPhase.SAVING_TO_WS)
                self._save_lpg_document(taxpayer.id, coe, ws_result, tipo_documento=tipo_doc)
                base.total_procesados_ok += 1
                logger.info(
                    "COE_PROCESS_WS_OK | taxpayer_id=%s empresa=%s coe=%s tipo=%s",
                    taxpayer.id,
                    taxpayer.empresa,
                    coe,
                    tipo_doc,
                )
            except Exception as exc:
                # Defensa en profundidad: si el parser SOAP rompe porque la respuesta
                # tiene elementos de ajuste cuando esperábamos liquidación, reintentar
                # con ajusteXCoeConsultar. Solo si NO veníamos ya del path de ajuste.
                if not is_ajuste_html and tipo_doc != "AJUSTE" and self._is_ajuste_parser_error(exc):
                    try:
                        logger.info(
                            "COE_IS_AJUSTE | taxpayer_id=%s coe=%s retrying with ajusteXCoeConsultar (parser exception)",
                            taxpayer.id, coe,
                        )
                        ws_result = ws_client.call_ajuste_x_coe(int(coe), pdf="N")
                        emit_ws_phase(ExtractionPhase.SAVING_TO_WS)
                        self._save_lpg_document(
                            taxpayer.id, coe, ws_result, tipo_documento="AJUSTE"
                        )
                        base.total_procesados_ok += 1
                        logger.info(
                            "COE_PROCESS_WS_OK | taxpayer_id=%s empresa=%s coe=%s tipo=AJUSTE (parser-fallback)",
                            taxpayer.id,
                            taxpayer.empresa,
                            coe,
                        )
                        continue
                    except Exception as exc_retry:
                        exc = exc_retry

                db.session.rollback()
                base.total_procesados_error += 1
                base.coes_error.append({"coe": coe, "error": str(exc)})
                logger.exception(
                    "COE_PROCESS_WS_ERROR | taxpayer_id=%s empresa=%s coe=%s",
                    taxpayer.id,
                    taxpayer.empresa,
                    coe,
                )

        if base.total_procesados_error == 0:
            base.outcome = "done"
        elif base.total_procesados_ok > 0:
            base.outcome = "partial"
        else:
            base.outcome = "error"
        if base.outcome != "done" and not base.error:
            base.error = "Se detectaron errores en liquidacionXCoeConsultar."
            base.failure_phase = ExtractionPhase.SAVING_TO_WS if last_emitted_phase == ExtractionPhase.SAVING_TO_WS else ExtractionPhase.DOWNLOADING_COE
            base.failure_error_type = "unknown"
        if base.outcome == "done" and on_phase is not None:
            try:
                on_phase(ExtractionPhase.FINISHED, PHASE_MESSAGES_ES[ExtractionPhase.FINISHED])
            except Exception:
                logger.exception("PIPELINE_ON_PHASE_CALLBACK_ERROR | phase=FINISHED")
        logger.info(
            "Taxpayer finished | id=%s empresa=%s outcome=%s detectados=%s nuevos=%s omitidos=%s ok_ws=%s error_ws=%s",
            taxpayer.id,
            taxpayer.empresa,
            base.outcome,
            base.total_coes_detectados,
            base.total_coes_nuevos,
            base.total_omitidos_existentes,
            base.total_procesados_ok,
            base.total_procesados_error,
        )
        return base

    def _resolve_clave_fiscal(self, taxpayer: Taxpayer) -> str:
        cipher = (taxpayer.clave_fiscal_encrypted or "").strip()
        if not cipher or is_placeholder_secret(cipher):
            raise ValueError(
                f"Cliente id={taxpayer.id} sin clave fiscal real cargada."
            )
        try:
            return decrypt_secret(cipher)
        except ValueError as exc:
            raise ValueError(
                f"No se pudo descifrar la clave fiscal del cliente id={taxpayer.id}."
            ) from exc

    def _validate_taxpayer_ws_config(self, taxpayer: Taxpayer) -> None:
        validate_taxpayer_ws_config(taxpayer)

    def _build_ws_client_for_taxpayer(self, taxpayer: Taxpayer) -> ArcaWslpgClient:
        return build_ws_client_for_taxpayer(taxpayer)

    def _coe_exists(self, taxpayer_id: int, coe: str) -> bool:
        return coe_already_exists(taxpayer_id, coe) is not None

    def _is_ajuste_error(self, ws_result: dict[str, Any]) -> bool:
        """Detecta si la respuesta WSLPG contiene error 1861 (COE es un ajuste)."""
        data = ws_result.get("data", {}) if isinstance(ws_result, dict) else {}
        errores = data.get("errores", {}) if isinstance(data, dict) else {}
        error_list = errores.get("error", []) if isinstance(errores, dict) else []
        if isinstance(error_list, dict):
            error_list = [error_list]
        return any(str(e.get("codigo")) == "1861" for e in error_list if isinstance(e, dict))

    def _is_ajuste_parser_error(self, exc: BaseException) -> bool:
        """Detecta si la excepción del parser SOAP delata un payload de ajuste.

        Cuando ARCA devuelve un ajuste sin error 1861 explícito, el cliente SOAP
        encuentra elementos como `ajusteCredito`/`ajusteDebito` que no encajan
        en el schema de liquidación.
        """
        message = str(exc).casefold()
        return "ajustecredito" in message or "ajustedebito" in message

    def _save_lpg_document(
        self, taxpayer_id: int, coe: str, ws_result: dict[str, Any],
        tipo_documento: str = "LPG",
    ) -> None:
        save_lpg_document_from_ws(taxpayer_id, coe, ws_result, tipo_documento)

    def _find_key(self, value: Any, keys: set[str]) -> Any:
        from .lpg_document_utils import _find_key
        return _find_key(value, keys)

    def _to_int(self, value: Any) -> int | None:
        from .lpg_document_utils import _to_int
        return _to_int(value)

    def _to_str(self, value: Any) -> str | None:
        from .lpg_document_utils import _to_str
        return _to_str(value)
