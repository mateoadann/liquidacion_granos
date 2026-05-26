# LPG Direct URL Fallback for SEARCH_SERVICE Failures

- Date: 2026-05-26
- Status: Approved (design)
- Scope: `backend/app/integrations/playwright/lpg_consulta_client.py`, `backend/app/services/lpg_playwright_pipeline.py`, and the persisted per-client detail object exposed by the extraction job API.

## Problem

The Playwright RPA that scrapes "Liquidación Primaria de Granos" (LPG) from AFIP/ARCA logs into the portal, types `"liquidacion primaria de granos"` into the AFIP search combobox, waits for the autocomplete dropdown, and clicks the suggestion. Clicking the suggestion opens the LPG service in a new popup (`expect_popup()`), which becomes `service_page`.

This step fails intermittently. The dropdown either never renders the LPG suggestion or renders it too late for the current waits, and `_wait_for_lpg_service_link` raises `PlaywrightFlowError(phase=SEARCH_SERVICE)`. The failure has no reproducible trigger — it surfaces in production as:

```json
{
  "current_phase": "SEARCH_SERVICE",
  "error": "Playwright: No se encontró el servicio 'Liquidación Primaria de Granos' en el buscador de AFIP.",
  "failure_message_technical": "ARCA_SLOW_AFTER_DROPDOWN | Playwright: No se encontró el servicio 'Liquidación Primaria de Granos' en el buscador de AFIP.",
  "failure_message_user": "Arca tardó demasiado en responder. Reintentará automáticamente.",
  "failure_phase": "SEARCH_SERVICE",
  "status": "error"
}
```

The job is later retried by the existing auto-retry scheduler, but the same path runs again and can fail again, hurting throughput.

## Goal

Add a deterministic fallback that bypasses the AFIP search combobox when it misbehaves: open a new tab inside the same authenticated browser context and navigate directly to the LPG service URL. Capture which method actually opened the service so we can measure how often the fallback rescues a job.

Non-goals:

- Do not change the happy path when the search combobox works.
- Do not change the auto-retry scheduler, the job model surface in the frontend, env vars, or any other pipeline phase.
- Do not introduce a strategy abstraction; the fallback is a single, named code path.

## Approach (selected: Option A)

Modify only `LpgConsultaClient._open_lpg_service`. When the existing search-box flow raises `PlaywrightFlowError(phase=SEARCH_SERVICE)`, catch it, attempt the direct-URL fallback once, and either return the resulting `service_page` or re-raise the original error.

Other options considered and rejected:

- Option B (`ServiceOpenStrategy` plug-in interface): over-engineered for a single fallback today.
- Option C (always skip the search combobox): removes the existing path as a safety net; deferred until we have evidence the direct URL is robust across all account configurations.

## Design

### Flow inside `_open_lpg_service`

```
LOGIN_CONFIRMED
    │
    ▼
SEARCH_SERVICE  (type query, await dropdown)
    │
    ▼
search-box path:
  ├─ _click_dropdown_suggestion
  ├─ _wait_for_lpg_service_link          ← may raise PlaywrightFlowError(SEARCH_SERVICE)
  ├─ _open_service_popup                 (popup → service_page)
  └─ _wait_for_service_page_ready
    │
    ├─ success  → service_open_method = "search_box"
    │             return service_page
    │
    └─ PlaywrightFlowError(phase=SEARCH_SERVICE)
           │
           ▼
        direct-URL fallback:
          ├─ context.new_page()
          ├─ goto("https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp",
          │       wait_until="networkidle")
          ├─ _wait_for_service_page_ready(direct_page)
          │
          ├─ success → service_open_method = "direct_url"
          │            return direct_page (becomes service_page)
          │
          └─ failure → close direct_page, re-raise the ORIGINAL
                       PlaywrightFlowError (preserves phase, message,
                       dropdown_clicked diagnostics)
```

Errors from non-`SEARCH_SERVICE` phases (e.g. `OPEN_SERVICE` popup timeout, `LOGIN_START`) are NOT caught — they propagate unchanged.

### Code changes

`backend/app/integrations/playwright/lpg_consulta_client.py`:

1. Add class constant:
   ```python
   LPG_DIRECT_URL = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
   ```

2. Add instance state alongside `_search_dropdown_clicked`:
   ```python
   self._service_open_method: str | None = None
   ```
   Reset to `None` at the start of every extraction run (same place where `_search_dropdown_clicked` is reset, around line 295).

3. Wrap the search-box body of `_open_lpg_service` in a `try/except PlaywrightFlowError as exc`. The current implementation already has a retry-on-`OPEN_SERVICE` block; that stays. The new fallback runs only when `exc.phase == ExtractionPhase.SEARCH_SERVICE`:
   ```python
   except PlaywrightFlowError as exc:
       if exc.phase is not ExtractionPhase.SEARCH_SERVICE:
           raise
       logger.warning(
           "PLAYWRIGHT_SERVICE_FALLBACK_TO_DIRECT_URL | empresa=%s reason=%s",
           empresa, exc,
       )
       try:
           service_page = self._open_lpg_service_via_direct_url(
               login_page, timeout_ms, empresa,
           )
           self._service_open_method = "direct_url"
           return service_page
       except PlaywrightFlowError:
           raise exc  # preserve original SEARCH_SERVICE diagnostics
   ```

4. On the happy path, set `self._service_open_method = "search_box"` immediately before returning `service_page`.

5. New private method:
   ```python
   def _open_lpg_service_via_direct_url(
       self, login_page: Page, timeout_ms: int, empresa: str,
   ) -> Page:
       logger.info(
           "PLAYWRIGHT_SERVICE_DIRECT_URL_START | empresa=%s url=%s",
           empresa, self.LPG_DIRECT_URL,
       )
       context = login_page.context
       direct_page = context.new_page()
       try:
           direct_page.goto(self.LPG_DIRECT_URL, wait_until="networkidle")
           self._wait_for_service_page_ready(direct_page, timeout_ms, empresa)
       except Exception:
           logger.warning(
               "PLAYWRIGHT_SERVICE_DIRECT_URL_FAIL | empresa=%s url=%s",
               empresa, direct_page.url,
           )
           try:
               direct_page.close()
           except Exception:
               pass
           raise
       logger.info(
           "PLAYWRIGHT_SERVICE_DIRECT_URL_OK | empresa=%s url=%s",
           empresa, direct_page.url,
       )
       return direct_page
   ```
   It reuses `_wait_for_service_page_ready`, which already validates `EMPRESA_FORM_SELECTOR` and the "Seleccione la Empresa" text — same readiness contract as the popup path.

6. Just before `_open_lpg_service` returns, emit:
   ```python
   logger.info(
       "PLAYWRIGHT_SERVICE_OPEN_METHOD | empresa=%s method=%s",
       empresa, self._service_open_method,
   )
   ```

### Pipeline (`backend/app/services/lpg_playwright_pipeline.py`)

- Add a field to the result dataclass that mirrors the pattern of `failure_phase` / `failure_dropdown_clicked`:
  ```python
  service_open_method: str | None = None
  ```
- After a successful client run, copy `client._service_open_method` into `base.service_open_method`. (On failure leave it as `None`.)

### Persistence and API surface

- `service_open_method` MUST appear in the per-client detail object the API returns inside `clients[]` for an extraction job — same level as `failure_phase`, `metrics`, `status`. Acceptance is "the user sees `service_open_method` in the JSON they pasted in the brief".
- Implementation note (verified at apply time): the existing `ExtractionJob` detail container is the natural home. If the detail per client is a JSONB / serialized dict, add the key there and add no migration. If the model requires a typed column, stop and confirm with the user before adding an Alembic migration; do not add a column unilaterally.
- The frontend is not in scope for this change, but the field is harmless to render later (`search_box` | `direct_url` | `null`).

### Logs (grep contract)

| Event                                    | Log key                                       | When                                                                |
| ---------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------- |
| Fallback triggered                       | `PLAYWRIGHT_SERVICE_FALLBACK_TO_DIRECT_URL`   | Search-box raised `SEARCH_SERVICE`, about to attempt direct URL.    |
| Direct URL navigation started            | `PLAYWRIGHT_SERVICE_DIRECT_URL_START`         | Entering `_open_lpg_service_via_direct_url`.                        |
| Direct URL navigation succeeded          | `PLAYWRIGHT_SERVICE_DIRECT_URL_OK`            | `_wait_for_service_page_ready` returned on the direct page.         |
| Direct URL navigation failed             | `PLAYWRIGHT_SERVICE_DIRECT_URL_FAIL`          | `goto` or readiness check raised.                                   |
| Final method chosen for this extraction  | `PLAYWRIGHT_SERVICE_OPEN_METHOD`              | Just before `_open_lpg_service` returns.                            |

Operator can run `rg PLAYWRIGHT_SERVICE_OPEN_METHOD` on backend logs to count `search_box` vs `direct_url` over time.

## Error handling

- If both the search-box path and the direct-URL fallback fail, the original `PlaywrightFlowError(phase=SEARCH_SERVICE, dropdown_clicked=…)` is re-raised. This preserves:
  - `failure_phase = "SEARCH_SERVICE"` in the job
  - The user-facing message "Arca tardó demasiado en responder. Reintentará automáticamente."
  - The auto-retry scheduler behavior (transient → retried)
  - The diagnostic screenshot already taken inside `_log_search_service_diagnostics` BEFORE the fallback attempt (untouched).
- A `PlaywrightFlowError` from any other phase (e.g. `OPEN_SERVICE`, `LOGIN_START`) propagates without entering the fallback.
- Any non-`PlaywrightFlowError` exception (Playwright timeout, network) inside the direct-URL path is caught only to close `direct_page`, then propagates.

## Out of scope

- Strategy/plug-in abstractions.
- Skipping the search combobox by default.
- Retrying the search box more than once after the direct URL fails.
- Frontend changes (the new field is consumable later without code change in this PR).
- Alembic migration: only added if the existing detail container cannot store the field, and only after explicit user confirmation.

## Testing

New unit tests under `backend/tests/unit/` using mocked Playwright `Page`/`BrowserContext`:

1. `test_open_lpg_service_marks_method_search_box_on_happy_path`
   Happy path through the search box → `service_open_method == "search_box"`, `new_page()` is NOT called on the context.

2. `test_open_lpg_service_falls_back_to_direct_url_on_search_failure`
   Force `_wait_for_lpg_service_link` to raise `PlaywrightFlowError(SEARCH_SERVICE)`. Assert that:
   - `context.new_page()` is called once
   - `goto(LPG_DIRECT_URL, wait_until="networkidle")` is called
   - `_wait_for_service_page_ready` is called on the new page
   - Returned page is the new page
   - `service_open_method == "direct_url"`

3. `test_open_lpg_service_reraises_original_error_when_direct_url_also_fails`
   Force both paths to fail. Assert the raised exception is the ORIGINAL search-box `PlaywrightFlowError` (same message, `phase=SEARCH_SERVICE`, `dropdown_clicked` preserved). Assert `direct_page.close()` was called.

4. `test_open_lpg_service_does_not_fallback_on_non_search_phase`
   Force the search-box path to raise `PlaywrightFlowError(phase=OPEN_SERVICE)`. Assert `context.new_page()` is NOT called and the original error propagates.

5. `test_service_open_method_propagates_to_pipeline_result`
   In the pipeline-level test, run one client through a mocked `LpgConsultaClient` whose `_service_open_method` is `"direct_url"`. Assert the resulting per-client detail object contains `service_open_method == "direct_url"`.

No integration test against real AFIP is added — the direct URL only behaves correctly with a live authenticated session.

## Acceptance criteria

- A job whose AFIP search dropdown does not surface the LPG suggestion now completes successfully via the direct URL, instead of erroring with `failure_phase=SEARCH_SERVICE`.
- The per-client detail object returned by the extraction job API contains `service_open_method` set to either `"search_box"` or `"direct_url"` for successful clients.
- Failing both paths preserves the exact same error shape and user-facing message as today.
- `rg PLAYWRIGHT_SERVICE_OPEN_METHOD` in backend logs yields one line per successful client extraction, with `method=search_box` or `method=direct_url`.
- No changes to env vars, Docker compose, frontend, scheduler, or DB schema unless explicitly confirmed at apply time.
