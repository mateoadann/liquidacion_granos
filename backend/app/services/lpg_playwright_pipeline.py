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
    PlaywrightFlowError,
)
from ..models import LpgDocument, Taxpayer
from .certificate_validator import (
    CertificateValidationError,
    validate_certificate_and_key_paths,
)
from .crypto_service import decrypt_secret, is_placeholder_secret
from .datos_limpios_builder import DatosLimpiosBuilder
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TaxpayerPipelineResult:
    taxpayer_id: int
    empresa: str
    cuit: str
    cuit_representado: str
    ok: bool
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


@dataclass(slots=True)
class PipelineRunResult:
    started_at: str
    finished_at: str
    fecha_desde: str
    fecha_hasta: str
    taxpayers_total: int
    taxpayers_ok: int
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
            "taxpayers_error": self.taxpayers_error,
            "results": [asdict(item) for item in self.results],
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
        type_delay_ms: int = 80,
        slow_mo_ms: int = 0,
        post_action_delay_ms: int = 0,
        login_max_retries: int = 1,
        humanize_delays: bool = True,
        retry_max_attempts: int = 2,
        retry_base_delay_ms: int = 1000,
        on_taxpayer_start: Callable[[Taxpayer], None] | None = None,
        on_taxpayer_finish: Callable[[TaxpayerPipelineResult], None] | None = None,
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
            result = self._process_taxpayer(
                taxpayer=taxpayer,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                headless=headless,
                timeout_ms=timeout_ms,
                type_delay_ms=type_delay_ms,
                slow_mo_ms=slow_mo_ms,
                post_action_delay_ms=post_action_delay_ms,
                login_max_retries=login_max_retries,
                humanize_delays=humanize_delays,
                retry_max_attempts=retry_max_attempts,
                retry_base_delay_ms=retry_base_delay_ms,
            )
            results.append(result)
            if on_taxpayer_finish:
                on_taxpayer_finish(result)
            logger.info(
                "Playwright pipeline taxpayer result | id=%s empresa=%s ok=%s detectados=%s nuevos=%s omitidos=%s ok_ws=%s error_ws=%s error=%s",
                result.taxpayer_id,
                result.empresa,
                result.ok,
                result.total_coes_detectados,
                result.total_coes_nuevos,
                result.total_omitidos_existentes,
                result.total_procesados_ok,
                result.total_procesados_error,
                result.error,
            )

        finished = now_cordoba_naive()
        taxpayers_ok = sum(1 for item in results if item.ok)
        taxpayers_error = len(results) - taxpayers_ok
        return PipelineRunResult(
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            taxpayers_total=len(results),
            taxpayers_ok=taxpayers_ok,
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
        type_delay_ms: int,
        slow_mo_ms: int,
        post_action_delay_ms: int,
        login_max_retries: int,
        humanize_delays: bool,
        retry_max_attempts: int,
        retry_base_delay_ms: int,
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
            ok=False,
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

        try:
            logger.info(
                "CLIENT_PLAYWRIGHT_START | taxpayer_id=%s empresa=%s",
                taxpayer.id,
                taxpayer.empresa,
            )
            consulta = ArcaLpgPlaywrightClient().run(
                LpgConsultaRequest(
                    credentials=LpgCredentials(cuit=taxpayer.cuit, clave_fiscal=clave),
                    empresa=taxpayer.empresa,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    headless=headless,
                    timeout_ms=timeout_ms,
                    type_delay_ms=type_delay_ms,
                    slow_mo_ms=slow_mo_ms,
                    post_action_delay_ms=post_action_delay_ms,
                    login_max_retries=login_max_retries,
                    humanize_delays=humanize_delays,
                    retry_max_attempts=retry_max_attempts,
                    retry_base_delay_ms=retry_base_delay_ms,
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
            logger.error(
                "Taxpayer playwright error | id=%s empresa=%s error=%s",
                taxpayer.id,
                taxpayer.empresa,
                base.error,
            )
            return base
        except Exception as exc:
            base.error = f"Playwright inesperado: {exc}"
            logger.exception(
                "Taxpayer playwright unexpected error | id=%s empresa=%s",
                taxpayer.id,
                taxpayer.empresa,
            )
            return base

        base.consulta = consulta.to_dict()
        base.total_rows = consulta.total_rows
        base.total_coes_detectados = consulta.total_coes

        ws_client = self._build_ws_client_for_taxpayer(taxpayer)
        logger.info(
            "CLIENT_COE_PROCESSING_START | taxpayer_id=%s empresa=%s total_coes=%s",
            taxpayer.id,
            taxpayer.empresa,
            len(consulta.coes),
        )
        for coe in consulta.coes:
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
                "COE_PROCESS_START | taxpayer_id=%s empresa=%s coe=%s",
                taxpayer.id,
                taxpayer.empresa,
                coe,
            )
            try:
                ws_result = ws_client.call_liquidacion_x_coe(int(coe), pdf="N")
                tipo_doc = "LPG"
                if self._is_ajuste_error(ws_result):
                    logger.info(
                        "COE_IS_AJUSTE | taxpayer_id=%s coe=%s retrying with ajusteXCoeConsultar",
                        taxpayer.id, coe,
                    )
                    ws_result = ws_client.call_ajuste_x_coe(int(coe), pdf="N")
                    tipo_doc = "AJUSTE"
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
                db.session.rollback()
                base.total_procesados_error += 1
                base.coes_error.append({"coe": coe, "error": str(exc)})
                logger.exception(
                    "COE_PROCESS_WS_ERROR | taxpayer_id=%s empresa=%s coe=%s",
                    taxpayer.id,
                    taxpayer.empresa,
                    coe,
                )

        base.ok = base.total_procesados_error == 0
        if not base.ok and not base.error:
            base.error = "Se detectaron errores en liquidacionXCoeConsultar."
        logger.info(
            "Taxpayer finished | id=%s empresa=%s ok=%s detectados=%s nuevos=%s omitidos=%s ok_ws=%s error_ws=%s",
            taxpayer.id,
            taxpayer.empresa,
            base.ok,
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
        if not taxpayer.cuit_representado:
            raise ValueError(f"Cliente id={taxpayer.id} sin cuit_representado.")
        if not taxpayer.cert_crt_path or not taxpayer.cert_key_path:
            raise ValueError(f"Cliente id={taxpayer.id} sin certificados cargados.")
        try:
            validate_certificate_and_key_paths(taxpayer.cert_crt_path, taxpayer.cert_key_path)
        except CertificateValidationError as exc:
            raise ValueError(
                f"Certificados inválidos para cliente id={taxpayer.id}: {exc}"
            ) from exc

    def _build_ws_client_for_taxpayer(self, taxpayer: Taxpayer) -> ArcaWslpgClient:
        config = ArcaDiscoveryConfig.from_env()
        config.environment = taxpayer.ambiente or config.environment
        config.cuit_representada = taxpayer.cuit_representado
        config.cert_path = taxpayer.cert_crt_path
        config.key_path = taxpayer.cert_key_path

        ta_base = config.ta_path or os.getenv("ARCA_TA_PATH") or "/tmp/ta"
        config.ta_path = str(Path(ta_base) / f"taxpayer_{taxpayer.id}")
        return ArcaWslpgClient(config=config)

    def _coe_exists(self, taxpayer_id: int, coe: str) -> bool:
        return (
            LpgDocument.query.filter_by(taxpayer_id=taxpayer_id, coe=coe).first()
            is not None
        )

    def _is_ajuste_error(self, ws_result: dict[str, Any]) -> bool:
        """Detecta si la respuesta WSLPG contiene error 1861 (COE es un ajuste)."""
        data = ws_result.get("data", {}) if isinstance(ws_result, dict) else {}
        errores = data.get("errores", {}) if isinstance(data, dict) else {}
        error_list = errores.get("error", []) if isinstance(errores, dict) else []
        if isinstance(error_list, dict):
            error_list = [error_list]
        return any(str(e.get("codigo")) == "1861" for e in error_list if isinstance(e, dict))

    def _save_lpg_document(
        self, taxpayer_id: int, coe: str, ws_result: dict[str, Any],
        tipo_documento: str = "LPG",
    ) -> None:
        data = ws_result.get("data") if isinstance(ws_result, dict) else ws_result
        document = LpgDocument()
        document.taxpayer_id = taxpayer_id
        document.coe = coe
        document.tipo_documento = tipo_documento
        document.pto_emision = self._to_int(self._find_key(data, {"ptoEmision", "pto_emision"}))
        document.nro_orden = self._to_int(self._find_key(data, {"nroOrden", "nro_orden"}))
        document.estado = self._to_str(self._find_key(data, {"estado", "estadoLiquidacion"}))
        document.raw_data = ws_result
        db.session.add(document)
        db.session.commit()

        builder = DatosLimpiosBuilder()
        builder.process_document(document)

    def _find_key(self, value: Any, keys: set[str]) -> Any:
        lowered = {item.casefold() for item in keys}
        stack = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, child in current.items():
                    if str(key).casefold() in lowered:
                        return child
                    stack.append(child)
            elif isinstance(current, list):
                stack.extend(current)
        return None

    def _to_int(self, value: Any) -> int | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    def _to_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
