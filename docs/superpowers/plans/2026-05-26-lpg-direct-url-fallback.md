# LPG Direct URL Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the Playwright RPA cannot find "Liquidación Primaria de Granos" via the AFIP search combobox (`PlaywrightFlowError(phase=SEARCH_SERVICE)`), open a new tab inside the same authenticated `BrowserContext` to `https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp` and continue the flow there. Persist which method opened the service (`search_box` | `direct_url`) in the per-client detail of the extraction job so we can measure how often the fallback rescues a run.

**Architecture:** Single point of change: `LpgConsultaClient._open_lpg_service` catches `PlaywrightFlowError(phase=SEARCH_SERVICE)` and invokes a new `_open_lpg_service_via_direct_url` helper that reuses `_wait_for_service_page_ready` for readiness validation. Method telemetry travels via a new `_service_open_method` attribute on the client → new `service_open_method` field on `TaxpayerPipelineResult` → key in the `progress["clients"][i]` dict written by the worker. No DB migration. No frontend, scheduler, env-var, or other pipeline changes.

**Tech Stack:** Python 3.x, Playwright (sync API), Flask + SQLAlchemy + Alembic backend, pytest with `unittest.mock`. Branch: `feature/063-lpg-direct-url-fallback`.

**Reference spec:** `docs/superpowers/specs/2026-05-26-lpg-direct-url-fallback-design.md`.

---

## File Structure

Files touched by this plan:

- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
  - Add `LPG_DIRECT_URL` class constant
  - Add `self._service_open_method` state (reset alongside `_search_dropdown_clicked`)
  - Add `_open_lpg_service_via_direct_url` helper
  - Wrap search-box body of `_open_lpg_service` in try/except that triggers the fallback only for `phase == SEARCH_SERVICE`
  - Set `self._service_open_method` on each successful exit and log `PLAYWRIGHT_SERVICE_OPEN_METHOD`
- Modify: `backend/app/services/lpg_playwright_pipeline.py`
  - Add `service_open_method: str | None = None` to `TaxpayerPipelineResult`
  - Copy `client._service_open_method` into `base.service_open_method` after a successful client run
- Modify: `backend/app/workers/playwright_jobs.py`
  - Extend `_update_progress_state` signature with `service_open_method: str | None = None`, write it into the client dict on `done` / `partial` / `error`
  - At the result-processing call site, pass `service_open_method=result.service_open_method`
  - At job init (where each client dict is built), seed `"service_open_method": None`
- Create: `backend/tests/unit/test_lpg_consulta_client_service_open.py`
  - 4 unit tests around `_open_lpg_service` and `_open_lpg_service_via_direct_url`
- Create: `backend/tests/unit/test_lpg_pipeline_service_open_method.py`
  - 1 unit test that verifies `service_open_method` propagation through `TaxpayerPipelineResult`

No frontend, no Alembic migration, no env vars, no Docker compose changes.

---

## Task 1: Pipeline dataclass field for `service_open_method`

Add the field first; downstream code can reference it.

**Files:**
- Modify: `backend/app/services/lpg_playwright_pipeline.py`
- Test: `backend/tests/unit/test_lpg_pipeline_service_open_method.py` (created in this task)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_lpg_pipeline_service_open_method.py`:

```python
from app.services.lpg_playwright_pipeline import (
    TaxpayerPipelineResult,
    _taxpayer_result_to_dict,
)


def test_taxpayer_pipeline_result_defaults_service_open_method_to_none() -> None:
    result = TaxpayerPipelineResult(
        taxpayer_id=1,
        empresa="ACME SRL",
        cuit="20111111112",
        cuit_representado="20111111112",
    )

    assert result.service_open_method is None


def test_taxpayer_pipeline_result_serializes_service_open_method() -> None:
    result = TaxpayerPipelineResult(
        taxpayer_id=1,
        empresa="ACME SRL",
        cuit="20111111112",
        cuit_representado="20111111112",
    )
    result.service_open_method = "direct_url"

    payload = _taxpayer_result_to_dict(result)

    assert payload["service_open_method"] == "direct_url"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/unit/test_lpg_pipeline_service_open_method.py -v
```

Expected: FAIL — `AttributeError: 'TaxpayerPipelineResult' object has no attribute 'service_open_method'`.

- [ ] **Step 3: Add the field to the dataclass**

In `backend/app/services/lpg_playwright_pipeline.py`, inside the `TaxpayerPipelineResult` dataclass, add (immediately after `failure_dropdown_clicked: bool = False`):

```python
    # Which path opened the LPG service for this run: "search_box" | "direct_url"
    service_open_method: str | None = None
```

`_taxpayer_result_to_dict` uses `asdict(item)`, so the field is serialized automatically — no change needed there.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/unit/test_lpg_pipeline_service_open_method.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lpg_playwright_pipeline.py \
        backend/tests/unit/test_lpg_pipeline_service_open_method.py
git commit -m "feat(pipeline): add service_open_method to TaxpayerPipelineResult"
```

---

## Task 2: Client state for `_service_open_method` and `LPG_DIRECT_URL` constant

Introduce the attribute and constant. Still no behavior change.

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
- Test: `backend/tests/unit/test_lpg_consulta_client_service_open.py` (created in this task)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_lpg_consulta_client_service_open.py`:

```python
from app.integrations.playwright.lpg_consulta_client import LpgConsultaClient


def test_lpg_consulta_client_exposes_direct_url_constant() -> None:
    assert (
        LpgConsultaClient.LPG_DIRECT_URL
        == "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    )


def test_lpg_consulta_client_initializes_service_open_method_to_none() -> None:
    client = LpgConsultaClient()

    assert client._service_open_method is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: FAIL — `AttributeError` on both the class constant and the instance attribute.

- [ ] **Step 3: Add the constant and instance attribute**

In `backend/app/integrations/playwright/lpg_consulta_client.py`:

Add the class constant near the other URL/selector constants on `LpgConsultaClient` (next to `LANDING_URL`, `EMPRESA_FORM_SELECTOR`, etc.):

```python
    LPG_DIRECT_URL = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
```

In `__init__` (around line 145, alongside `self._search_dropdown_clicked: bool = False`), add:

```python
        self._service_open_method: str | None = None
```

In `run` (around line 295, where `self._search_dropdown_clicked = False` is reset at the start of an extraction), add immediately after that line:

```python
        self._service_open_method = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py \
        backend/tests/unit/test_lpg_consulta_client_service_open.py
git commit -m "feat(playwright): add LPG_DIRECT_URL and _service_open_method state"
```

---

## Task 3: `_open_lpg_service` marks happy path as `search_box`

Before introducing the fallback, lock in the happy-path label so the next task can layer the fallback on top.

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
- Test: `backend/tests/unit/test_lpg_consulta_client_service_open.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_lpg_consulta_client_service_open.py`:

```python
from unittest.mock import MagicMock

from app.integrations.playwright.lpg_consulta_client import LpgConsultaClient


def _build_client_with_stubbed_open_path(
    open_service_returns: object,
    wait_ready_returns: object | None = None,
    wait_ready_side_effect: BaseException | None = None,
) -> tuple[LpgConsultaClient, MagicMock]:
    client = LpgConsultaClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(
        return_value=(MagicMock(name="service_link"), "Liquidación primaria de granos")
    )
    client._open_service_popup = MagicMock(return_value=open_service_returns)
    if wait_ready_side_effect is not None:
        client._wait_for_service_page_ready = MagicMock(
            side_effect=wait_ready_side_effect
        )
    else:
        client._wait_for_service_page_ready = MagicMock(return_value=wait_ready_returns)

    login_page = MagicMock(name="login_page")
    search = MagicMock(name="search_combobox")
    login_page.get_by_role.return_value = search
    return client, login_page


def test_open_lpg_service_marks_method_search_box_on_happy_path() -> None:
    service_page = MagicMock(name="service_page")
    client, login_page = _build_client_with_stubbed_open_path(
        open_service_returns=service_page
    )

    result = client._open_lpg_service(
        login_page=login_page,
        timeout_ms=10_000,
        type_delay_ms=10,
        empresa="ACME SRL",
        humanize_delays=False,
    )

    assert result is service_page
    assert client._service_open_method == "search_box"
    login_page.context.new_page.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py::test_open_lpg_service_marks_method_search_box_on_happy_path -v
```

Expected: FAIL — `_service_open_method` stays `None` on the happy path.

- [ ] **Step 3: Set `_service_open_method = "search_box"` on success**

In `backend/app/integrations/playwright/lpg_consulta_client.py`, inside `_open_lpg_service`, locate the happy-path return (the `try/except PlaywrightFlowError` block that today returns `service_page` after `_wait_for_service_page_ready(service_page, ...)`, around line 579). Immediately before that `return service_page`, add:

```python
            self._service_open_method = "search_box"
```

Locate the retry-success return (the second `return service_page` near line 606, after the retry attempt with `exact_link`). Immediately before that `return service_page`, add:

```python
        self._service_open_method = "search_box"
```

Do NOT add the assignment yet to any direct-URL path — that arrives in Task 4.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: PASS (3 passed total in this file).

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py \
        backend/tests/unit/test_lpg_consulta_client_service_open.py
git commit -m "feat(playwright): mark search-box path as service_open_method=search_box"
```

---

## Task 4: Direct-URL fallback helper `_open_lpg_service_via_direct_url`

Implement the helper in isolation: it accepts a `login_page`, opens a new tab on the same `context` pointing at `LPG_DIRECT_URL`, validates with `_wait_for_service_page_ready`, and returns the new page.

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
- Test: `backend/tests/unit/test_lpg_consulta_client_service_open.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_lpg_consulta_client_service_open.py`:

```python
def test_open_lpg_service_via_direct_url_navigates_and_validates() -> None:
    client = LpgConsultaClient()
    client._wait_for_service_page_ready = MagicMock()

    direct_page = MagicMock(name="direct_page")
    direct_page.url = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    context = MagicMock(name="context")
    context.new_page.return_value = direct_page
    login_page = MagicMock(name="login_page")
    login_page.context = context

    returned = client._open_lpg_service_via_direct_url(
        login_page, timeout_ms=10_000, empresa="ACME SRL"
    )

    assert returned is direct_page
    context.new_page.assert_called_once_with()
    direct_page.goto.assert_called_once_with(
        LpgConsultaClient.LPG_DIRECT_URL,
        wait_until="networkidle",
    )
    client._wait_for_service_page_ready.assert_called_once_with(
        direct_page, 10_000, "ACME SRL"
    )
    direct_page.close.assert_not_called()


def test_open_lpg_service_via_direct_url_closes_page_on_failure() -> None:
    from app.integrations.playwright.lpg_consulta_client import (
        ExtractionPhase,
        PlaywrightFlowError,
    )

    client = LpgConsultaClient()
    failure = PlaywrightFlowError("not ready", phase=ExtractionPhase.OPEN_SERVICE)
    client._wait_for_service_page_ready = MagicMock(side_effect=failure)

    direct_page = MagicMock(name="direct_page")
    direct_page.url = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    context = MagicMock(name="context")
    context.new_page.return_value = direct_page
    login_page = MagicMock(name="login_page")
    login_page.context = context

    import pytest as _pytest

    with _pytest.raises(PlaywrightFlowError):
        client._open_lpg_service_via_direct_url(
            login_page, timeout_ms=10_000, empresa="ACME SRL"
        )

    direct_page.close.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: FAIL — `_open_lpg_service_via_direct_url` does not exist.

- [ ] **Step 3: Add the helper**

In `backend/app/integrations/playwright/lpg_consulta_client.py`, add this method on `LpgConsultaClient` (place it right after `_open_lpg_service`, before `_click_dropdown_suggestion`):

```python
    def _open_lpg_service_via_direct_url(
        self, login_page: Page, timeout_ms: int, empresa: str
    ) -> Page:
        """Fallback path: open the LPG service in a new tab on the same context.

        Reuses the authenticated cookies of `login_page.context`, so the new tab
        lands on the LPG service directly. Validates with the same readiness
        check used by the search-box path.
        """
        logger.info(
            "PLAYWRIGHT_SERVICE_DIRECT_URL_START | empresa=%s url=%s",
            empresa,
            self.LPG_DIRECT_URL,
        )
        context = login_page.context
        direct_page = context.new_page()
        try:
            direct_page.goto(self.LPG_DIRECT_URL, wait_until="networkidle")
            self._wait_for_service_page_ready(direct_page, timeout_ms, empresa)
        except Exception:
            logger.warning(
                "PLAYWRIGHT_SERVICE_DIRECT_URL_FAIL | empresa=%s url=%s",
                empresa,
                getattr(direct_page, "url", self.LPG_DIRECT_URL),
            )
            try:
                direct_page.close()
            except Exception:
                pass
            raise
        logger.info(
            "PLAYWRIGHT_SERVICE_DIRECT_URL_OK | empresa=%s url=%s",
            empresa,
            getattr(direct_page, "url", self.LPG_DIRECT_URL),
        )
        return direct_page
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: PASS (5 passed total in this file).

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py \
        backend/tests/unit/test_lpg_consulta_client_service_open.py
git commit -m "feat(playwright): add _open_lpg_service_via_direct_url helper"
```

---

## Task 5: Wire the fallback into `_open_lpg_service`

Trigger the helper only when the search-box path raises `PlaywrightFlowError(phase=SEARCH_SERVICE)`. On success, mark `_service_open_method = "direct_url"`. On failure, re-raise the original error to preserve diagnostics and the auto-retry contract.

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
- Test: `backend/tests/unit/test_lpg_consulta_client_service_open.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_lpg_consulta_client_service_open.py`:

```python
def test_open_lpg_service_falls_back_to_direct_url_on_search_service_error() -> None:
    from app.integrations.playwright.lpg_consulta_client import (
        ExtractionPhase,
        PlaywrightFlowError,
    )

    client = LpgConsultaClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(
        side_effect=PlaywrightFlowError(
            "No se encontró el servicio",
            phase=ExtractionPhase.SEARCH_SERVICE,
            dropdown_clicked=True,
        )
    )

    direct_page = MagicMock(name="direct_page")
    direct_page.url = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    context = MagicMock(name="context")
    context.new_page.return_value = direct_page

    login_page = MagicMock(name="login_page")
    login_page.context = context
    login_page.get_by_role.return_value = MagicMock(name="search_combobox")

    client._wait_for_service_page_ready = MagicMock()

    result = client._open_lpg_service(
        login_page=login_page,
        timeout_ms=10_000,
        type_delay_ms=10,
        empresa="ACME SRL",
        humanize_delays=False,
    )

    assert result is direct_page
    assert client._service_open_method == "direct_url"
    context.new_page.assert_called_once_with()
    direct_page.goto.assert_called_once_with(
        LpgConsultaClient.LPG_DIRECT_URL, wait_until="networkidle"
    )


def test_open_lpg_service_reraises_original_error_when_direct_url_also_fails() -> None:
    from app.integrations.playwright.lpg_consulta_client import (
        ExtractionPhase,
        PlaywrightFlowError,
    )

    original = PlaywrightFlowError(
        "No se encontró el servicio",
        phase=ExtractionPhase.SEARCH_SERVICE,
        dropdown_clicked=True,
    )

    client = LpgConsultaClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(side_effect=original)

    direct_page = MagicMock(name="direct_page")
    direct_page.url = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    context = MagicMock(name="context")
    context.new_page.return_value = direct_page

    login_page = MagicMock(name="login_page")
    login_page.context = context
    login_page.get_by_role.return_value = MagicMock(name="search_combobox")

    client._wait_for_service_page_ready = MagicMock(
        side_effect=PlaywrightFlowError(
            "direct url failed",
            phase=ExtractionPhase.OPEN_SERVICE,
        )
    )

    import pytest as _pytest

    with _pytest.raises(PlaywrightFlowError) as exc_info:
        client._open_lpg_service(
            login_page=login_page,
            timeout_ms=10_000,
            type_delay_ms=10,
            empresa="ACME SRL",
            humanize_delays=False,
        )

    raised = exc_info.value
    assert raised is original
    assert raised.phase == ExtractionPhase.SEARCH_SERVICE
    assert raised.dropdown_clicked is True
    direct_page.close.assert_called_once()
    assert client._service_open_method is None


def test_open_lpg_service_does_not_fallback_on_open_service_phase() -> None:
    from app.integrations.playwright.lpg_consulta_client import (
        ExtractionPhase,
        PlaywrightFlowError,
    )

    open_service_error = PlaywrightFlowError(
        "popup timed out",
        phase=ExtractionPhase.OPEN_SERVICE,
    )

    client = LpgConsultaClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(
        return_value=(MagicMock(name="service_link"), "Liquidación primaria de granos")
    )
    client._open_service_popup = MagicMock(side_effect=open_service_error)

    context = MagicMock(name="context")
    login_page = MagicMock(name="login_page")
    login_page.context = context
    login_page.get_by_role.return_value = MagicMock(name="search_combobox")

    # Also fail the retry path so the original OPEN_SERVICE error surfaces.
    exact_link = MagicMock(name="exact_link")
    exact_link.count.return_value = 0
    login_page.locator.return_value = exact_link

    import pytest as _pytest

    with _pytest.raises(PlaywrightFlowError) as exc_info:
        client._open_lpg_service(
            login_page=login_page,
            timeout_ms=10_000,
            type_delay_ms=10,
            empresa="ACME SRL",
            humanize_delays=False,
        )

    assert exc_info.value.phase == ExtractionPhase.OPEN_SERVICE
    context.new_page.assert_not_called()
    assert client._service_open_method is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: the three new tests FAIL (current code propagates the `SEARCH_SERVICE` error instead of falling back).

- [ ] **Step 3: Refactor `_open_lpg_service` to wrap the search-box body and invoke the fallback**

In `backend/app/integrations/playwright/lpg_consulta_client.py`, restructure `_open_lpg_service` so that the current body (from `_emit_phase(ExtractionPhase.SEARCH_SERVICE)` through the retry `return service_page`) lives inside an inner local function `_open_via_search_box()` that returns `service_page` on success.

Replace the body of `_open_lpg_service` with:

```python
    def _open_lpg_service(
        self,
        login_page: Page,
        timeout_ms: int,
        type_delay_ms: int,
        empresa: str,
        humanize_delays: bool = True,
    ) -> Page:
        def _open_via_search_box() -> Page:
            self._emit_phase(ExtractionPhase.SEARCH_SERVICE)
            logger.info("PLAYWRIGHT_SEARCH_SERVICE_START | empresa=%s", empresa)
            search = login_page.get_by_role(
                "combobox", name=re.compile(r"Buscador", re.IGNORECASE)
            )
            search.click()
            search.fill("")
            search.type("liquidacion primaria de granos", delay=type_delay_ms)
            logger.info(
                "PLAYWRIGHT_SEARCH_SERVICE_TYPED | empresa=%s query=Liquidación primaria de granos",
                empresa,
            )
            self._post_action_pause(
                login_page, 800, "search_typed", empresa, humanize_delays
            )

            clicked = self._click_dropdown_suggestion(login_page, timeout_ms, empresa)
            if not clicked:
                logger.warning(
                    "PLAYWRIGHT_SEARCH_DROPDOWN_FALLBACK | empresa=%s action=press_enter",
                    empresa,
                )
                search.press("Enter")

            service_link, link_text = self._wait_for_lpg_service_link(
                login_page, timeout_ms
            )
            logger.info(
                "PLAYWRIGHT_SERVICE_LINK_CHOSEN | empresa=%s link_text=%s",
                empresa,
                link_text,
            )
            self._emit_phase(ExtractionPhase.OPEN_SERVICE)
            service_page = self._open_service_popup(
                login_page, service_link, timeout_ms, empresa
            )

            try:
                self._wait_for_service_page_ready(service_page, timeout_ms, empresa)
                self._service_open_method = "search_box"
                return service_page
            except PlaywrightFlowError:
                logger.warning("PLAYWRIGHT_SERVICE_RETRY_OPEN | empresa=%s", empresa)
                try:
                    service_page.close()
                except Exception:
                    pass

            exact_link = login_page.locator(
                "a",
                has_text=re.compile(
                    r"^\s*Liquidaci[oó]n\s+primaria\s+de\s+granos\s*$",
                    re.IGNORECASE,
                ),
            ).first
            if exact_link.count() == 0:
                raise PlaywrightFlowError(
                    "Se abrió una ventana inválida del servicio y no se encontró el link exacto "
                    "'Liquidación primaria de granos' para reintentar.",
                    phase=ExtractionPhase.OPEN_SERVICE,
                )

            exact_text = _normalize_text(exact_link.inner_text())
            logger.info(
                "PLAYWRIGHT_SERVICE_LINK_CHOSEN | empresa=%s link_text=%s attempt=retry",
                empresa,
                exact_text,
            )
            service_page = self._open_service_popup(
                login_page, exact_link, timeout_ms, empresa
            )
            self._wait_for_service_page_ready(service_page, timeout_ms, empresa)
            self._service_open_method = "search_box"
            return service_page

        try:
            return _open_via_search_box()
        except PlaywrightFlowError as exc:
            if exc.phase is not ExtractionPhase.SEARCH_SERVICE:
                raise
            logger.warning(
                "PLAYWRIGHT_SERVICE_FALLBACK_TO_DIRECT_URL | empresa=%s reason=%s",
                empresa,
                exc,
            )
            try:
                service_page = self._open_lpg_service_via_direct_url(
                    login_page, timeout_ms, empresa
                )
            except Exception:
                # Preserve the ORIGINAL SEARCH_SERVICE diagnostics (message,
                # phase, dropdown_clicked) so the auto-retry scheduler keeps
                # behaving as today.
                raise exc from None
            self._service_open_method = "direct_url"
            return service_page
```

Notes:
- The inner function MUST still set `self._service_open_method = "search_box"` on each successful return so behavior matches Task 3.
- `raise exc from None` is intentional: we want the original `SEARCH_SERVICE` exception to surface, not the direct-URL one.
- The diagnostic screenshot is taken inside `_wait_for_lpg_service_link` (`_log_search_service_diagnostics`) BEFORE the exception bubbles up, so it is preserved even when the fallback rescues the run.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: PASS — all 8 tests in this file (2 from Task 2, 1 from Task 3, 2 from Task 4, 3 from Task 5).

- [ ] **Step 5: Final log line on `_open_lpg_service`**

Right before each `return` in `_open_lpg_service` (the happy-path `return service_page` from `_open_via_search_box()` AND the `return service_page` after the direct-URL fallback), the method log already runs. To make the chosen method greppable at the top level, add one final log just BEFORE the `_open_lpg_service` method ends. Place this single log line in the outer function — i.e., after the `try/except` that wraps `_open_via_search_box`, capturing whatever value `self._service_open_method` ended up with.

Refactor the outer block at the end of `_open_lpg_service` to:

```python
        try:
            service_page = _open_via_search_box()
        except PlaywrightFlowError as exc:
            if exc.phase is not ExtractionPhase.SEARCH_SERVICE:
                raise
            logger.warning(
                "PLAYWRIGHT_SERVICE_FALLBACK_TO_DIRECT_URL | empresa=%s reason=%s",
                empresa,
                exc,
            )
            try:
                service_page = self._open_lpg_service_via_direct_url(
                    login_page, timeout_ms, empresa
                )
            except Exception:
                raise exc from None
            self._service_open_method = "direct_url"

        logger.info(
            "PLAYWRIGHT_SERVICE_OPEN_METHOD | empresa=%s method=%s",
            empresa,
            self._service_open_method,
        )
        return service_page
```

(The two `return service_page` lines inside `_open_via_search_box` become a single `return service_page` because the inner function returns the value to the outer scope. Adjust the inner function to do `return service_page` at the two success points unchanged — the outer block above captures the value into `service_page` and returns it after the log.)

- [ ] **Step 6: Re-run tests to confirm no regression**

```bash
cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v
```

Expected: PASS — all 8 tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py \
        backend/tests/unit/test_lpg_consulta_client_service_open.py
git commit -m "feat(playwright): fallback to direct LPG URL on SEARCH_SERVICE failures"
```

---

## Task 6: Propagate `service_open_method` from client to pipeline result

The pipeline already wraps `LpgConsultaClient` and copies success/failure metadata into `TaxpayerPipelineResult`. Extend that copy to include `service_open_method`.

**Files:**
- Modify: `backend/app/services/lpg_playwright_pipeline.py`
- Test: `backend/tests/unit/test_lpg_pipeline_service_open_method.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_lpg_pipeline_service_open_method.py`:

```python
from unittest.mock import MagicMock, patch

from app.services.lpg_playwright_pipeline import (
    LpgPlaywrightPipelineService,
    TaxpayerPipelineResult,
)


def _make_taxpayer_stub(taxpayer_id: int = 1):
    taxpayer = MagicMock(name=f"taxpayer_{taxpayer_id}")
    taxpayer.id = taxpayer_id
    taxpayer.empresa = "ACME SRL"
    taxpayer.cuit = "20111111112"
    taxpayer.cuit_representado = "20111111112"
    return taxpayer


def test_pipeline_copies_service_open_method_from_client(monkeypatch) -> None:
    """When the LpgConsultaClient reports a method, the pipeline must mirror it."""
    service = LpgPlaywrightPipelineService()

    consulta = MagicMock()
    consulta.total_rows = 0
    consulta.total_coes = 0
    consulta.to_dict.return_value = {"rows": []}

    captured_client = {}

    def fake_run_consulta(self_client, request):
        # Simulate that the client used the direct-URL fallback.
        self_client._service_open_method = "direct_url"
        captured_client["client"] = self_client
        return consulta

    monkeypatch.setattr(
        "app.integrations.playwright.lpg_consulta_client.LpgConsultaClient.run",
        fake_run_consulta,
    )

    # Avoid real WS construction and COE processing.
    service._build_ws_client_for_taxpayer = MagicMock(return_value=MagicMock())
    service._process_coes_for_taxpayer = MagicMock(
        return_value=TaxpayerPipelineResult(
            taxpayer_id=1,
            empresa="ACME SRL",
            cuit="20111111112",
            cuit_representado="20111111112",
        )
    )

    taxpayer = _make_taxpayer_stub()
    result = service._run_taxpayer_extraction(
        taxpayer=taxpayer,
        fecha_desde="2026-01-01",
        fecha_hasta="2026-01-31",
        headless=True,
        timeout_ms=10_000,
        type_delay_ms=10,
        slow_mo_ms=0,
        post_action_delay_ms=0,
        login_max_retries=1,
        humanize_delays=False,
        retry_max_attempts=1,
        retry_base_delay_ms=10,
        on_phase=None,
    )

    assert result.service_open_method == "direct_url"
```

Note: this test assumes the per-taxpayer extraction lives in a method like `_run_taxpayer_extraction`. If the actual private method name in `lpg_playwright_pipeline.py` differs, adjust the call site to whichever method instantiates `LpgConsultaClient` and builds the `TaxpayerPipelineResult`. The contract being tested is unchanged: after that method runs, `result.service_open_method` must equal whatever the client recorded.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/unit/test_lpg_pipeline_service_open_method.py -v
```

Expected: FAIL — `service_open_method` is `None` because the pipeline does not yet copy it from the client.

- [ ] **Step 3: Copy `_service_open_method` from the client into the result**

In `backend/app/services/lpg_playwright_pipeline.py`, locate the per-taxpayer extraction block where, after a successful `LpgConsultaClient` run, the code currently does:

```python
        base.consulta = consulta.to_dict()
        base.total_rows = consulta.total_rows
        base.total_coes_detectados = consulta.total_coes
```

Immediately after those three lines (the block starting around line 312), add:

```python
        base.service_open_method = client._service_open_method
```

`client` is the `LpgConsultaClient` instance already in scope at that point (the same one whose `_search_dropdown_clicked` is read on the exception paths around lines 289 and 303). No need to set the field on failure paths — it stays `None`, which is the documented behavior.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/unit/test_lpg_pipeline_service_open_method.py -v
```

Expected: PASS (3 passed in this file).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lpg_playwright_pipeline.py \
        backend/tests/unit/test_lpg_pipeline_service_open_method.py
git commit -m "feat(pipeline): propagate service_open_method from client to result"
```

---

## Task 7: Surface `service_open_method` in the job progress dict

Plug the field into the worker so it appears in `progress["clients"][i]` (the same dict already serving `failure_phase`, `failure_message_user`, etc.).

**Files:**
- Modify: `backend/app/workers/playwright_jobs.py`

- [ ] **Step 1: Inspect the worker structure (manual sanity check)**

Run:

```bash
cd backend && rg -n "service_open_method|_update_progress_state|\"clients\"" app/workers/playwright_jobs.py
```

Confirm:
- `_update_progress_state` (around line 78) is where each client dict is mutated on status transitions.
- The job init around line 53 builds each client dict with `"failure_phase": None, "failure_message_user": None`. We add `"service_open_method": None` there.
- The call site that finalizes a client (around line 400) invokes `_update_progress_state(..., status=result.outcome, metrics=...)`. We add `service_open_method=result.service_open_method`.

- [ ] **Step 2: Add the field to the initial client dict**

In `backend/app/workers/playwright_jobs.py`, locate the dict literal that builds the initial per-client entries (around line 53, where `"failure_phase": None`, `"failure_message_user": None` already live). Add the key alongside them:

```python
                "failure_phase": None,
                "failure_message_user": None,
                "failure_message_technical": None,
                "service_open_method": None,
```

(Keep the existing keys; only add the new line. If `failure_message_technical` is not present in your file at that exact spot, just insert `"service_open_method": None,` somewhere between `failure_message_user` and the closing brace of the dict — order doesn't matter.)

- [ ] **Step 3: Extend `_update_progress_state` to accept and persist the field**

Change the signature and the `done`/`partial`/`error` branch of `_update_progress_state` (around line 78). The function currently looks like:

```python
def _update_progress_state(
    extraction_job_id: int,
    payload: dict[str, Any],
    *,
    taxpayer_id: int,
    status: str,
    error: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
```

Add a parameter:

```python
def _update_progress_state(
    extraction_job_id: int,
    payload: dict[str, Any],
    *,
    taxpayer_id: int,
    status: str,
    error: str | None = None,
    metrics: dict[str, Any] | None = None,
    service_open_method: str | None = None,
) -> None:
```

In the branch `elif status in {"done", "partial", "error"}:` (around line 106), inside the matching client block, after `client["error"] = error`, add:

```python
            client["service_open_method"] = service_open_method
```

(No special handling needed for `status == "running"`. The initial dict already seeds the key to `None`, and we overwrite it once when the client finishes. If the same client gets re-run by retry logic, the field is set by the next `done`/`partial`/`error` call.)

- [ ] **Step 4: Pass `service_open_method` at the call site**

Locate the `_update_progress_state` call that finalizes a taxpayer's run (around line 400, right after `result = ... .run(...)`). It currently looks like:

```python
            _update_progress_state(
                extraction_job_id,
                payload,
                taxpayer_id=result.taxpayer_id,
                status=result.outcome,
                error=result.error,
                metrics={
                    "total_coes_detectados": result.total_coes_detectados,
                    "total_coes_nuevos": result.total_coes_nuevos,
                    "total_procesados_ok": result.total_procesados_ok,
                    "total_procesados_error": result.total_procesados_error,
                },
            )
```

Add the kwarg:

```python
            _update_progress_state(
                extraction_job_id,
                payload,
                taxpayer_id=result.taxpayer_id,
                status=result.outcome,
                error=result.error,
                metrics={
                    "total_coes_detectados": result.total_coes_detectados,
                    "total_coes_nuevos": result.total_coes_nuevos,
                    "total_procesados_ok": result.total_procesados_ok,
                    "total_procesados_error": result.total_procesados_error,
                },
                service_open_method=result.service_open_method,
            )
```

- [ ] **Step 5: Run the full backend test suite to catch regressions**

```bash
cd backend && pytest -q
```

Expected: PASS. Any pre-existing failures unrelated to this change must already exist on `dev`; if a previously-green test breaks, fix the cause before committing.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/playwright_jobs.py
git commit -m "feat(worker): expose service_open_method in job progress payload"
```

---

## Task 8: End-to-end manual verification + static checks

Verify the change is consistent at the file/type level and lint cleanly.

**Files:**
- All files modified in tasks 1-7.

- [ ] **Step 1: Static checks pass**

```bash
cd backend && python -m compileall app tests
```

Expected: no errors.

- [ ] **Step 2: Full backend suite green**

```bash
cd backend && pytest -q
```

Expected: PASS for the whole suite.

- [ ] **Step 3: Grep the new log markers exist in code**

```bash
rg -n "PLAYWRIGHT_SERVICE_(DIRECT_URL|OPEN_METHOD|FALLBACK_TO_DIRECT_URL)" \
   backend/app/integrations/playwright/lpg_consulta_client.py
```

Expected: 5 matches — `_START`, `_OK`, `_FAIL`, `_FALLBACK_TO_DIRECT_URL`, `_OPEN_METHOD`.

- [ ] **Step 4: Manual sanity diff against the spec acceptance criteria**

Open `docs/superpowers/specs/2026-05-26-lpg-direct-url-fallback-design.md` "Acceptance criteria" section and confirm each bullet maps to a passing test or a code change:

1. Job rescued via direct URL → tests in Task 5.
2. `service_open_method` in per-client detail → Tasks 6 + 7.
3. Both-failed preserves error shape → Task 5 (`test_open_lpg_service_reraises_original_error_when_direct_url_also_fails`).
4. `PLAYWRIGHT_SERVICE_OPEN_METHOD` log line per successful client → Task 5 step 5.
5. No env / DB / scheduler / frontend changes → confirmed by file list.

- [ ] **Step 5: Push the branch**

```bash
git push -u origin feature/063-lpg-direct-url-fallback
```

- [ ] **Step 6: Open the PR**

```bash
gh pr create --base dev --title "feat(playwright): direct-URL fallback for LPG SEARCH_SERVICE failures" --body "$(cat <<'EOF'
## Summary
- When the AFIP search combobox does not surface the "Liquidación Primaria de Granos" suggestion, open a new tab in the same authenticated `BrowserContext` to `https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp` and validate readiness with the existing `_wait_for_service_page_ready` check.
- Expose `service_open_method` (`search_box` | `direct_url`) in the per-client detail of the extraction job so we can measure how often the fallback rescues a run.
- Preserve today's error shape (`failure_phase=SEARCH_SERVICE`, `dropdown_clicked`, user message) when BOTH paths fail, so the existing auto-retry scheduler keeps working.

## Test plan
- [ ] `cd backend && pytest tests/unit/test_lpg_consulta_client_service_open.py -v` (all 8 pass)
- [ ] `cd backend && pytest tests/unit/test_lpg_pipeline_service_open_method.py -v` (all 3 pass)
- [ ] `cd backend && pytest -q` (full suite green)
- [ ] `cd backend && python -m compileall app tests`
- [ ] Trigger an extraction in homologación and confirm `service_open_method` appears in the job progress JSON for each finished client.
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Problem (SEARCH_SERVICE intermittent failure) → Tasks 4 + 5 add the fallback.
- Approach Option A (single point of change in `_open_lpg_service`) → Task 5 wraps the body in an inner function and adds the catch-and-fallback.
- New `LPG_DIRECT_URL` constant → Task 2.
- `_service_open_method` instance state, reset per `run()` → Task 2.
- `_open_lpg_service_via_direct_url` helper → Task 4.
- Fallback triggers only on `phase == SEARCH_SERVICE`, re-raises original on failure → Task 5 (including a regression test for `phase=OPEN_SERVICE`).
- `service_open_method` propagated to `TaxpayerPipelineResult` → Tasks 1 + 6.
- Field surfaced in `progress["clients"][i]` (no migration) → Task 7.
- Log markers `PLAYWRIGHT_SERVICE_DIRECT_URL_{START,OK,FAIL}`, `PLAYWRIGHT_SERVICE_FALLBACK_TO_DIRECT_URL`, `PLAYWRIGHT_SERVICE_OPEN_METHOD` → Tasks 4 + 5.
- Out-of-scope items (frontend, env vars, migration, scheduler) → untouched in the file structure.
- Tests 1-5 in the spec → covered by Tasks 3 (#1), 5 (#2, #3, #4), 6 (#5).

**Placeholder scan:** no `TBD`, `TODO`, "appropriate", "similar to" placeholders. Each step shows the exact code or command.

**Type consistency:** `_service_open_method`, `service_open_method`, `LPG_DIRECT_URL` are spelled identically across client → pipeline → worker. The log keys are spelled identically across the helper and the wrapper. The signature change to `_update_progress_state` uses a keyword-only parameter with `None` default, which is backwards-compatible with any other call site.

Plan ready.
