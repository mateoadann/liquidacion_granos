from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
import logging

from playwright.sync_api import (
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def _normalize_key(value: str | None) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.casefold().split())


@dataclass(slots=True)
class LpgCredentials:
    cuit: str
    clave_fiscal: str


@dataclass(slots=True)
class LpgConsultaRequest:
    credentials: LpgCredentials
    empresa: str
    fecha_desde: str
    fecha_hasta: str
    headless: bool = True
    timeout_ms: int = 30_000
    type_delay_ms: int = 80


@dataclass(slots=True)
class LpgConsultaResult:
    started_at: str
    finished_at: str
    empresa: str
    fecha_desde: str
    fecha_hasta: str
    total_rows: int
    total_coes: int
    headers: list[str]
    coes: list[str]

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "empresa": self.empresa,
            "fecha_desde": self.fecha_desde,
            "fecha_hasta": self.fecha_hasta,
            "total_rows": self.total_rows,
            "total_coes": self.total_coes,
            "headers": self.headers,
            "coes": self.coes,
        }


class PlaywrightFlowError(RuntimeError):
    """Error funcional del flujo Playwright en ARCA/AFIP."""


logger = logging.getLogger(__name__)


class ArcaLpgPlaywrightClient:
    LANDING_URL = "https://www.afip.gob.ar/landing/default.asp"
    EMPRESA_FORM_SELECTOR = "form[name='seleccionaEmpresaForm']"

    def run(self, request: LpgConsultaRequest) -> LpgConsultaResult:
        started = datetime.utcnow()
        logger.info(
            "PLAYWRIGHT_RUN_START | empresa=%s desde=%s hasta=%s timeout_ms=%s type_delay_ms=%s",
            request.empresa,
            request.fecha_desde,
            request.fecha_hasta,
            request.timeout_ms,
            request.type_delay_ms,
        )
        with sync_playwright() as playwright:
            headers, total_rows, coes = self._run_with_playwright(playwright, request)
        finished = datetime.utcnow()

        logger.info(
            "PLAYWRIGHT_RUN_FINISHED | empresa=%s total_rows=%s total_coes=%s",
            request.empresa,
            total_rows,
            len(coes),
        )

        return LpgConsultaResult(
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            empresa=request.empresa,
            fecha_desde=request.fecha_desde,
            fecha_hasta=request.fecha_hasta,
            total_rows=total_rows,
            total_coes=len(coes),
            headers=headers,
            coes=coes,
        )

    def _run_with_playwright(
        self, playwright: Playwright, request: LpgConsultaRequest
    ) -> tuple[list[str], int, list[str]]:
        logger.info("PLAYWRIGHT_BROWSER_LAUNCH | empresa=%s headless=%s", request.empresa, request.headless)
        browser = playwright.chromium.launch(headless=request.headless)
        context = browser.new_context()
        landing_page = context.new_page()

        login_page: Page | None = None
        service_page: Page | None = None

        try:
            login_page = self._login(landing_page, request)
            service_page = self._open_lpg_service(
                login_page,
                request.timeout_ms,
                request.type_delay_ms,
                request.empresa,
            )
            self._select_empresa(service_page, request.empresa, request.timeout_ms)
            self._open_consulta_recibidas(service_page, request.timeout_ms, request.empresa)
            self._set_fechas(
                service_page,
                request.fecha_desde,
                request.fecha_hasta,
                request.timeout_ms,
                request.empresa,
            )
            self._submit_consulta(service_page, request.timeout_ms, request.empresa)
            headers, total_rows, coes = self._read_results_coes(
                service_page,
                request.timeout_ms,
                request.empresa,
            )
            return headers, total_rows, coes
        finally:
            self._safe_logout(service_page, login_page)
            context.close()
            browser.close()

    def _login(self, landing_page: Page, request: LpgConsultaRequest) -> Page:
        logger.info("PLAYWRIGHT_NAVIGATE_LANDING | empresa=%s", request.empresa)
        landing_page.goto(self.LANDING_URL, wait_until="domcontentloaded")

        with landing_page.expect_popup() as popup_info:
            logger.info("PLAYWRIGHT_CLICK_INICIAR_SESION | empresa=%s", request.empresa)
            landing_page.get_by_role(
                "link", name=re.compile(r"Iniciar sesi[oó]n", re.IGNORECASE)
            ).click()
        login_page = popup_info.value
        login_page.wait_for_load_state("domcontentloaded")
        logger.info("PLAYWRIGHT_LOGIN_POPUP_READY | empresa=%s", request.empresa)

        logger.info("PLAYWRIGHT_FILL_CUIT | empresa=%s cuit=%s", request.empresa, self._mask_cuit(request.credentials.cuit))
        login_page.get_by_role("spinbutton").fill(request.credentials.cuit)
        logger.info("PLAYWRIGHT_SUBMIT_CUIT | empresa=%s", request.empresa)
        login_page.get_by_role("button", name=re.compile(r"Siguiente", re.IGNORECASE)).click()
        logger.info("PLAYWRIGHT_FILL_CLAVE | empresa=%s", request.empresa)
        login_page.get_by_role(
            "textbox", name=re.compile(r"(TU\s*CLAVE|Clave)", re.IGNORECASE)
        ).fill(request.credentials.clave_fiscal)
        logger.info("PLAYWRIGHT_SUBMIT_LOGIN | empresa=%s", request.empresa)
        login_page.get_by_role("button", name=re.compile(r"Ingresar", re.IGNORECASE)).click()

        login_ok, message = self._wait_for_login_result(login_page, request.timeout_ms)
        if not login_ok:
            logger.warning("PLAYWRIGHT_LOGIN_FAILED | empresa=%s error=%s", request.empresa, message)
            raise PlaywrightFlowError(message or "No se pudo confirmar el login.")
        logger.info("PLAYWRIGHT_LOGIN_CONFIRMED | empresa=%s", request.empresa)
        return login_page

    def _wait_for_login_result(self, login_page: Page, timeout_ms: int) -> tuple[bool, str | None]:
        deadline = time.monotonic() + (timeout_ms / 1000)
        error_locator = login_page.get_by_text(
            re.compile(r"clave o usuario incorrecto|error", re.IGNORECASE)
        )
        search_locator = login_page.get_by_role(
            "combobox", name=re.compile(r"Buscador", re.IGNORECASE)
        )

        while time.monotonic() < deadline:
            if error_locator.count() > 0 and error_locator.first.is_visible():
                return False, _normalize_text(error_locator.first.inner_text())
            if search_locator.count() > 0 and search_locator.first.is_visible():
                return True, None
            login_page.wait_for_timeout(250)
        return False, "Timeout esperando confirmación de login (Buscador no visible)."

    def _open_lpg_service(
        self,
        login_page: Page,
        timeout_ms: int,
        type_delay_ms: int,
        empresa: str,
    ) -> Page:
        logger.info("PLAYWRIGHT_SEARCH_SERVICE_START | empresa=%s", empresa)
        search = login_page.get_by_role("combobox", name=re.compile(r"Buscador", re.IGNORECASE))
        search.click()
        search.fill("")
        search.type("liquidacion primaria de granos", delay=type_delay_ms)
        search.press("Enter")
        logger.info(
            "PLAYWRIGHT_SEARCH_SERVICE_TYPED | empresa=%s query=liquidacion primaria de granos",
            empresa,
        )

        service_link, link_text = self._wait_for_lpg_service_link(login_page, timeout_ms)
        logger.info(
            "PLAYWRIGHT_SERVICE_LINK_CHOSEN | empresa=%s link_text=%s",
            empresa,
            link_text,
        )
        service_page = self._open_service_popup(login_page, service_link, timeout_ms, empresa)

        try:
            self._wait_for_service_page_ready(service_page, timeout_ms, empresa)
            return service_page
        except PlaywrightFlowError:
            logger.warning("PLAYWRIGHT_SERVICE_RETRY_OPEN | empresa=%s", empresa)
            try:
                service_page.close()
            except Exception:
                pass

        exact_link = login_page.locator(
            "a",
            has_text=re.compile(r"^\s*Liquidaci[oó]n\s+primaria\s+de\s+granos\s*$", re.IGNORECASE),
        ).first
        if exact_link.count() == 0:
            raise PlaywrightFlowError(
                "Se abrió una ventana inválida del servicio y no se encontró el link exacto "
                "'Liquidación primaria de granos' para reintentar."
            )

        exact_text = _normalize_text(exact_link.inner_text())
        logger.info(
            "PLAYWRIGHT_SERVICE_LINK_CHOSEN | empresa=%s link_text=%s attempt=retry",
            empresa,
            exact_text,
        )
        service_page = self._open_service_popup(login_page, exact_link, timeout_ms, empresa)
        self._wait_for_service_page_ready(service_page, timeout_ms, empresa)
        return service_page

    def _wait_for_lpg_service_link(self, login_page: Page, timeout_ms: int) -> tuple[Locator, str]:
        deadline = time.monotonic() + (timeout_ms / 1000)
        candidate_locators: list[tuple[Locator, str]] = [
            (
                login_page.locator(
                    "a",
                    has_text=re.compile(
                        r"^\s*Liquidaci[oó]n\s+primaria\s+de\s+granos\s*$",
                        re.IGNORECASE,
                    ),
                ),
                "exact_granos",
            ),
            (
                login_page.get_by_role(
                    "link", name=re.compile(r"Liquidaci[oó]n\s+primaria\s+de\s+granos", re.IGNORECASE)
                ),
                "role_granos",
            ),
            (
                login_page.get_by_role(
                    "link", name=re.compile(r"Liquidaci[oó]n\s+primaria\s+de", re.IGNORECASE)
                ),
                "role_fallback",
            ),
            (
                login_page.locator("a", has_text=re.compile(r"liquidaci[oó]n", re.IGNORECASE)),
                "text_fallback",
            ),
        ]

        while time.monotonic() < deadline:
            for locator, strategy in candidate_locators:
                try:
                    if locator.count() > 0 and locator.first.is_visible():
                        link_text = _normalize_text(locator.first.inner_text())
                        logger.info(
                            "PLAYWRIGHT_SERVICE_FOUND | strategy=%s link_text=%s",
                            strategy,
                            link_text,
                        )
                        return locator.first, link_text
                except Exception:
                    continue
            login_page.wait_for_timeout(250)

        available = self._detect_visible_service_links(login_page)
        details = f" Servicios visibles: {available[:10]}" if available else ""
        logger.warning("PLAYWRIGHT_SERVICE_NOT_FOUND | visible_services=%s", available[:10])
        raise PlaywrightFlowError(
            "No se encontró el servicio 'Liquidación Primaria de Granos' en el buscador de AFIP."
            + details
        )

    def _open_service_popup(
        self,
        login_page: Page,
        service_link: Locator,
        timeout_ms: int,
        empresa: str,
    ) -> Page:
        try:
            with login_page.expect_popup(timeout=timeout_ms) as popup_info:
                service_link.click()
            service_page = popup_info.value
        except PlaywrightTimeoutError as exc:
            logger.warning("PLAYWRIGHT_OPEN_SERVICE_POPUP_TIMEOUT | empresa=%s", empresa)
            raise PlaywrightFlowError(
                "El servicio LPG apareció en la búsqueda, pero no abrió una nueva ventana dentro del tiempo esperado."
            ) from exc
        logger.info("PLAYWRIGHT_OPEN_SERVICE_POPUP_OK | empresa=%s", empresa)
        service_page.wait_for_load_state("domcontentloaded")
        return service_page

    def _wait_for_service_page_ready(self, service_page: Page, timeout_ms: int, empresa: str) -> None:
        deadline = time.monotonic() + (timeout_ms / 1000)
        empresa_form = service_page.locator(self.EMPRESA_FORM_SELECTOR)
        select_empresa_text = service_page.get_by_text(
            re.compile(r"Seleccione\s+la\s+Empresa", re.IGNORECASE)
        )

        while time.monotonic() < deadline:
            form_ready = empresa_form.count() > 0 and empresa_form.first.is_visible()
            text_ready = select_empresa_text.count() > 0 and select_empresa_text.first.is_visible()
            if form_ready or text_ready:
                logger.info(
                    "PLAYWRIGHT_SERVICE_PAGE_READY | empresa=%s form_ready=%s text_ready=%s url=%s",
                    empresa,
                    form_ready,
                    text_ready,
                    service_page.url,
                )
                return
            service_page.wait_for_timeout(250)

        context = self._service_page_context(service_page)
        logger.warning(
            "PLAYWRIGHT_SERVICE_PAGE_INVALID | empresa=%s url=%s title=%s visible_buttons=%s",
            empresa,
            context["url"],
            context["title"],
            context["visible_buttons"][:10],
        )
        raise PlaywrightFlowError(
            "Se abrió una ventana distinta al selector de empresa de LPG. "
            f"URL: {context['url']} | Título: {context['title']} | "
            f"Botones visibles: {context['visible_buttons'][:10]}"
        )

    def _detect_visible_service_links(self, login_page: Page) -> list[str]:
        links = login_page.locator("a")
        available: list[str] = []
        for idx in range(links.count()):
            label = _normalize_text(links.nth(idx).inner_text())
            if not label:
                continue
            key = _normalize_key(label)
            if "liquidacion" in key or "granos" in key:
                available.append(label)
        return available

    def _select_empresa(self, service_page: Page, empresa_input: str, timeout_ms: int) -> None:
        logger.info("PLAYWRIGHT_SELECT_EMPRESA_START | empresa=%s", empresa_input)
        expected = _normalize_key(empresa_input)
        if not expected:
            raise PlaywrightFlowError("El campo empresa es obligatorio.")

        empresa_form = service_page.locator(self.EMPRESA_FORM_SELECTOR)
        empresa_form.wait_for(timeout=timeout_ms)

        named_candidates = empresa_form.get_by_role(
            "button",
            name=re.compile(re.escape(empresa_input), re.IGNORECASE),
        )
        for idx in range(named_candidates.count()):
            button = named_candidates.nth(idx)
            if not button.is_visible():
                continue
            label = self._extract_button_label(button)
            if label:
                button.click()
                logger.info("PLAYWRIGHT_SELECT_EMPRESA_OK | selected=%s mode=role_name", label)
                return

        candidates = self._resolve_empresa_candidates(service_page)
        if candidates.count() == 0:
            context = self._service_page_context(service_page)
            visible_buttons = context["visible_buttons"]
            logger.warning(
                "PLAYWRIGHT_SELECT_EMPRESA_NO_OPTIONS | empresa=%s url=%s title=%s visible_buttons=%s",
                empresa_input,
                context["url"],
                context["title"],
                visible_buttons[:10],
            )
            raise PlaywrightFlowError(
                "No se encontraron opciones de empresa para seleccionar. "
                f"URL: {context['url']} | Título: {context['title']} | "
                f"Botones visibles: {visible_buttons[:10]}"
            )

        first_partial: Locator | None = None
        available: list[str] = []
        for idx in range(candidates.count()):
            button = candidates.nth(idx)
            if not button.is_visible():
                continue
            label = self._extract_button_label(button)
            if not label:
                continue
            available.append(label)
            label_key = _normalize_key(label)
            if label_key == expected:
                button.click()
                logger.info("PLAYWRIGHT_SELECT_EMPRESA_OK | selected=%s mode=exact", label)
                return
            if expected in label_key and first_partial is None:
                first_partial = button

        if first_partial:
            first_partial.click()
            logger.info("PLAYWRIGHT_SELECT_EMPRESA_OK | selected=%s mode=partial", _normalize_text(first_partial.inner_text()))
            return

        raise PlaywrightFlowError(
            f"No se encontró la empresa '{empresa_input}'. Opciones detectadas: {available[:10]}"
        )

    def _resolve_empresa_candidates(self, service_page: Page) -> Locator:
        selectors = [
            "form[name='seleccionaEmpresaForm'] button",
            "button[onclick*='seleccionaEmpresa' i]",
            "form[id*='empresa' i] button",
            "button[name*='empresa' i]",
        ]

        for selector in selectors:
            locator = service_page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            if count > 0:
                logger.info(
                    "PLAYWRIGHT_SELECT_EMPRESA_CANDIDATES | selector=%s count=%s",
                    selector,
                    count,
                )
                return locator

        role_locator = service_page.get_by_role("button")
        logger.info(
            "PLAYWRIGHT_SELECT_EMPRESA_CANDIDATES | selector=role:button count=%s",
            role_locator.count(),
        )
        return role_locator

    def _detect_visible_buttons(self, service_page: Page) -> list[str]:
        buttons = service_page.get_by_role("button")
        labels: list[str] = []
        for idx in range(buttons.count()):
            button = buttons.nth(idx)
            try:
                if not button.is_visible():
                    continue
            except Exception:
                continue
            label = self._extract_button_label(button)
            if label:
                labels.append(label)
        return labels

    def _extract_button_label(self, button: Locator) -> str:
        try:
            text = _normalize_text(button.inner_text())
            if text:
                return text
        except Exception:
            pass
        for attr in ["aria-label", "value", "title"]:
            try:
                value = _normalize_text(button.get_attribute(attr))
            except Exception:
                value = ""
            if value:
                return value
        return ""

    def _service_page_context(self, service_page: Page) -> dict[str, object]:
        try:
            title = service_page.title()
        except Exception:
            title = ""
        return {
            "url": service_page.url,
            "title": title,
            "visible_buttons": self._detect_visible_buttons(service_page),
        }

    def _open_consulta_recibidas(self, service_page: Page, timeout_ms: int, empresa: str) -> None:
        logger.info("PLAYWRIGHT_OPEN_CONSULTA_RECIBIDAS_START | empresa=%s", empresa)
        service_page.get_by_role(
            "button", name=re.compile(r"Liquidaci[oó]n Primaria de Granos", re.IGNORECASE)
        ).click()
        target = service_page.get_by_role(
            "button", name=re.compile(r"Consulta Liquidaciones Recibidas", re.IGNORECASE)
        ).first
        target.wait_for(timeout=timeout_ms)
        target.click()
        logger.info("PLAYWRIGHT_OPEN_CONSULTA_RECIBIDAS_OK | empresa=%s", empresa)

    def _set_fechas(
        self,
        service_page: Page,
        fecha_desde: str,
        fecha_hasta: str,
        timeout_ms: int,
        empresa: str,
    ) -> None:
        logger.info("PLAYWRIGHT_SET_FECHAS | empresa=%s desde=%s hasta=%s", empresa, fecha_desde, fecha_hasta)
        input_desde = self._resolve_input_fecha_desde(service_page)
        input_hasta = self._resolve_input_fecha_hasta(service_page, input_desde)

        input_desde.wait_for(timeout=timeout_ms)
        input_desde.click()
        input_desde.fill(fecha_desde)

        input_hasta.wait_for(timeout=timeout_ms)
        input_hasta.click()
        input_hasta.fill(fecha_hasta)

    def _resolve_input_fecha_desde(self, service_page: Page) -> Locator:
        candidates = [
            service_page.get_by_role("textbox", name=re.compile(r"Fecha Desde|Desde", re.IGNORECASE)),
            service_page.locator("input[name='fechaDesdeStr']"),
            service_page.locator("input[name='fechaStr']"),
            service_page.locator("input[name*='fecha' i]").first,
        ]
        return self._first_existing_locator(candidates, "No se encontró input de Fecha Desde.")

    def _resolve_input_fecha_hasta(self, service_page: Page, input_desde: Locator) -> Locator:
        candidates = [
            service_page.get_by_role("textbox", name=re.compile(r"Fecha Hasta|Hasta", re.IGNORECASE)),
            service_page.locator("input[name='fechaHastaStr']"),
            service_page.locator("input[name='fechaHasta']"),
            service_page.locator("input[name*='fecha' i]").nth(1),
        ]
        fallback = self._first_existing_locator(candidates, "")
        if fallback.count() > 0:
            return fallback
        return input_desde

    def _first_existing_locator(self, candidates: list[Locator], error_message: str) -> Locator:
        for locator in candidates:
            try:
                if locator.count() > 0:
                    return locator.first
            except Exception:
                continue
        if not error_message:
            return candidates[-1]
        raise PlaywrightFlowError(error_message)

    def _submit_consulta(self, service_page: Page, timeout_ms: int, empresa: str) -> None:
        logger.info("PLAYWRIGHT_SUBMIT_CONSULTA | empresa=%s", empresa)
        service_page.get_by_role(
            "button", name=re.compile(r"Consultar Por Criterio|Buscar", re.IGNORECASE)
        ).first.click()
        service_page.locator("#tabla4").first.wait_for(timeout=timeout_ms)
        logger.info("PLAYWRIGHT_RESULTS_TABLE_READY | empresa=%s", empresa)

    def _read_results_coes(
        self,
        service_page: Page,
        timeout_ms: int,
        empresa: str,
    ) -> tuple[list[str], int, list[str]]:
        table = service_page.locator("#tabla4").first
        table.wait_for(timeout=timeout_ms)

        headers = [_normalize_text(value) for value in table.locator("th").all_inner_texts()]
        header_keys = [_normalize_key(header) for header in headers]
        coe_index = -1
        for idx, key in enumerate(header_keys):
            if key == "coe":
                coe_index = idx
                break

        rows_locator = table.locator("tr:has(td)")
        total_rows = rows_locator.count()

        seen: set[str] = set()
        coes: list[str] = []
        for idx in range(total_rows):
            row = rows_locator.nth(idx)
            cells = [_normalize_text(value) for value in row.locator("td").all_inner_texts()]
            if not cells:
                continue
            coe_value = self._extract_coe_from_row(cells, coe_index)
            if not coe_value or coe_value in seen:
                continue
            seen.add(coe_value)
            coes.append(coe_value)

        logger.info(
            "PLAYWRIGHT_COES_EXTRACTED | empresa=%s total_rows=%s total_coes=%s",
            empresa,
            total_rows,
            len(coes),
        )

        return headers, total_rows, coes

    def _mask_cuit(self, cuit: str) -> str:
        value = (cuit or "").strip()
        if len(value) <= 4:
            return "****"
        return f"{value[:2]}******{value[-2:]}"

    def _extract_coe_from_row(self, cells: list[str], coe_index: int) -> str:
        if 0 <= coe_index < len(cells):
            digits = re.sub(r"\D", "", cells[coe_index])
            if digits:
                return digits
        for cell in cells:
            digits = re.sub(r"\D", "", cell)
            if len(digits) >= 10:
                return digits
        return ""

    def _safe_logout(self, service_page: Page | None, login_page: Page | None) -> None:
        if service_page:
            try:
                service_page.once("dialog", lambda dialog: dialog.dismiss())
                logout_link = service_page.get_by_role(
                    "link", name=re.compile(r"Salir", re.IGNORECASE)
                )
                if logout_link.count() > 0:
                    logout_link.first.click()
            except Exception:
                pass
            try:
                service_page.close()
            except Exception:
                pass

        if login_page:
            try:
                icon = login_page.locator("#userIconoChico")
                if icon.count() > 0:
                    icon.first.click()
                close_button = login_page.get_by_role(
                    "button", name=re.compile(r"Cerrar sesi[oó]n", re.IGNORECASE)
                )
                if close_button.count() > 0:
                    close_button.first.click()
            except Exception:
                pass
            try:
                login_page.close()
            except Exception:
                pass
