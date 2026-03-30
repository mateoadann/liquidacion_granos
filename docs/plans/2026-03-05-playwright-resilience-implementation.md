# Playwright Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Mejorar la resiliencia del cliente Playwright de ARCA con ocultamiento de automatización, reintentos inteligentes y pausas humanizadas.

**Architecture:** Se modifica únicamente `lpg_consulta_client.py` agregando: (1) configuración de browser/context para ocultar automatización, (2) sistema de reintentos con máximo 2 intentos y detección de errores repetidos, (3) pausas con variación aleatoria. Sin dependencias nuevas.

**Tech Stack:** Python 3.11+, Playwright, pytest

---

## Task 1: Agregar parámetros de resiliencia a LpgConsultaRequest

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py:42-53`

**Step 1: Agregar nuevos campos al dataclass**

Ubicar el dataclass `LpgConsultaRequest` y agregar los nuevos parámetros:

```python
@dataclass(slots=True)
class LpgConsultaRequest:
    credentials: LpgCredentials
    empresa: str
    fecha_desde: str
    fecha_hasta: str
    headless: bool = True
    timeout_ms: int = 30_000
    type_delay_ms: int = 80
    slow_mo_ms: int = 0
    post_action_delay_ms: int = 0
    login_max_retries: int = 1
    # Nuevos parámetros de resiliencia
    humanize_delays: bool = True
    retry_max_attempts: int = 2
    retry_base_delay_ms: int = 1000
```

**Step 2: Verificar que el código compila**

Run: `cd backend && python -m compileall app/integrations/playwright/lpg_consulta_client.py -q`
Expected: Sin errores

**Step 3: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py
git commit -m "feat(playwright): add resilience parameters to LpgConsultaRequest"
```

---

## Task 2: Implementar función de delays humanizados

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
- Test: `backend/tests/unit/test_playwright_humanize.py`

**Step 1: Crear archivo de test**

```python
from __future__ import annotations

import pytest


def test_humanized_delay_returns_value_within_range():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()
    base_ms = 1000
    variance = 0.3

    results = [client._humanized_delay(base_ms, variance) for _ in range(100)]

    min_expected = int(base_ms * (1 - variance))  # 700
    max_expected = int(base_ms * (1 + variance))  # 1300

    assert all(min_expected <= r <= max_expected for r in results)
    assert len(set(results)) > 1  # Verificar que hay variación


def test_humanized_delay_with_zero_variance_returns_base():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    result = client._humanized_delay(500, variance_percent=0.0)

    assert result == 500


def test_humanized_delay_disabled_returns_base():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    result = client._humanized_delay(500, variance_percent=0.3, enabled=False)

    assert result == 500
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_playwright_humanize.py -v`
Expected: FAIL with "AttributeError: 'ArcaLpgPlaywrightClient' object has no attribute '_humanized_delay'"

**Step 3: Implementar el método**

Agregar al inicio del archivo el import de random, y agregar el método a la clase `ArcaLpgPlaywrightClient`:

```python
import random
```

```python
def _humanized_delay(
    self, base_ms: int, variance_percent: float = 0.3, enabled: bool = True
) -> int:
    """Retorna un delay con variación aleatoria de ±variance_percent."""
    if not enabled or variance_percent <= 0:
        return base_ms
    min_delay = int(base_ms * (1 - variance_percent))
    max_delay = int(base_ms * (1 + variance_percent))
    return random.randint(min_delay, max_delay)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_playwright_humanize.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/tests/unit/test_playwright_humanize.py backend/app/integrations/playwright/lpg_consulta_client.py
git commit -m "feat(playwright): add humanized delay function with tests"
```

---

## Task 3: Implementar clasificación de errores

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
- Test: `backend/tests/unit/test_playwright_humanize.py` (agregar tests)

**Step 1: Agregar tests de clasificación de errores**

Agregar al archivo de test existente:

```python
def test_classify_error_network_is_transient():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(Exception("net::ERR_CONNECTION_RESET"))

    assert classification.is_transient is True
    assert classification.error_type == "network"


def test_classify_error_timeout_is_transient():
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(PlaywrightTimeoutError("Timeout 30000ms"))

    assert classification.is_transient is True
    assert classification.error_type == "timeout"


def test_classify_error_auth_failed_is_not_transient():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(
        PlaywrightFlowError("clave o usuario incorrecto")
    )

    assert classification.is_transient is False
    assert classification.error_type == "auth_failed"


def test_classify_error_arca_unavailable_is_transient():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(
        PlaywrightFlowError("servicio no disponible")
    )

    assert classification.is_transient is True
    assert classification.error_type == "arca_unavailable"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_playwright_humanize.py::test_classify_error_network_is_transient -v`
Expected: FAIL with "AttributeError: 'ArcaLpgPlaywrightClient' object has no attribute '_classify_error'"

**Step 3: Implementar dataclass y método de clasificación**

Agregar después de `PlaywrightFlowError`:

```python
@dataclass(slots=True)
class ErrorClassification:
    """Clasificación de un error para decidir si reintentar."""
    is_transient: bool
    error_type: str  # "network", "timeout", "arca_unavailable", "auth_failed", "unknown"
    message: str
```

Agregar método a la clase `ArcaLpgPlaywrightClient`:

```python
def _classify_error(self, error: Exception) -> ErrorClassification:
    """Clasifica un error para determinar si es transitorio (reintentable)."""
    message = str(error).lower()

    # Errores de red
    if "net::err_" in message or "network" in message:
        return ErrorClassification(
            is_transient=True, error_type="network", message=str(error)
        )

    # Timeouts
    if isinstance(error, PlaywrightTimeoutError) or "timeout" in message:
        return ErrorClassification(
            is_transient=True, error_type="timeout", message=str(error)
        )

    # Errores de autenticación (no reintentar)
    auth_patterns = ["clave o usuario incorrecto", "credenciales", "clave fiscal"]
    if any(pattern in message for pattern in auth_patterns):
        return ErrorClassification(
            is_transient=False, error_type="auth_failed", message=str(error)
        )

    # ARCA no disponible (reintentar)
    arca_unavailable_patterns = [
        "servicio no disponible",
        "error del sistema",
        "intente más tarde",
        "sesión expirada",
        "tiempo de espera agotado",
    ]
    if any(pattern in message for pattern in arca_unavailable_patterns):
        return ErrorClassification(
            is_transient=True, error_type="arca_unavailable", message=str(error)
        )

    # Error desconocido - no reintentar por seguridad
    return ErrorClassification(
        is_transient=False, error_type="unknown", message=str(error)
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_playwright_humanize.py -v`
Expected: PASS (7 tests)

**Step 5: Actualizar exports en __init__.py**

Modificar `backend/app/integrations/playwright/__init__.py`:

```python
from .lpg_consulta_client import (
    ArcaLpgPlaywrightClient,
    ErrorClassification,
    LpgConsultaRequest,
    LpgConsultaResult,
    LpgCredentials,
    PlaywrightFlowError,
)

__all__ = [
    "ArcaLpgPlaywrightClient",
    "ErrorClassification",
    "LpgCredentials",
    "LpgConsultaRequest",
    "LpgConsultaResult",
    "PlaywrightFlowError",
]
```

**Step 6: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py \
        backend/app/integrations/playwright/__init__.py \
        backend/tests/unit/test_playwright_humanize.py
git commit -m "feat(playwright): add error classification for retry logic"
```

---

## Task 4: Configurar browser con ocultamiento de automatización

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py:126-136`

**Step 1: Definir constantes de configuración**

Agregar después de las constantes existentes en la clase:

```python
class ArcaLpgPlaywrightClient:
    LANDING_URL = "https://www.afip.gob.ar/landing/default.asp"
    EMPRESA_FORM_SELECTOR = "form[name='seleccionaEmpresaForm']"

    # Configuración anti-detección
    BROWSER_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
    ]
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    DEFAULT_VIEWPORT = {"width": 1366, "height": 768}
    WEBDRIVER_HIDE_SCRIPT = """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """
```

**Step 2: Modificar método _run_with_playwright**

Reemplazar la sección de lanzamiento del browser (líneas ~129-138):

```python
def _run_with_playwright(
    self, playwright: Playwright, request: LpgConsultaRequest
) -> tuple[list[str], int, list[str]]:
    logger.info(
        "PLAYWRIGHT_BROWSER_LAUNCH | empresa=%s headless=%s slow_mo_ms=%s",
        request.empresa, request.headless, request.slow_mo_ms,
    )
    browser = playwright.chromium.launch(
        headless=request.headless,
        slow_mo=request.slow_mo_ms,
        args=self.BROWSER_ARGS,
    )
    context = browser.new_context(
        user_agent=self.DEFAULT_USER_AGENT,
        viewport=self.DEFAULT_VIEWPORT,
        locale="es-AR",
        timezone_id="America/Argentina/Buenos_Aires",
    )
    context.add_init_script(self.WEBDRIVER_HIDE_SCRIPT)
    landing_page = context.new_page()
```

**Step 3: Verificar que el código compila**

Run: `cd backend && python -m compileall app/integrations/playwright/lpg_consulta_client.py -q`
Expected: Sin errores

**Step 4: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py
git commit -m "feat(playwright): configure browser to hide automation signals"
```

---

## Task 5: Implementar wrapper de reintentos

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`
- Test: `backend/tests/unit/test_playwright_humanize.py`

**Step 1: Agregar tests para el sistema de reintentos**

```python
def test_retry_wrapper_succeeds_first_attempt(mocker):
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()
    mock_operation = mocker.Mock(return_value="success")

    result = client._with_retry(
        operation=mock_operation,
        operation_name="test_op",
        max_attempts=2,
        base_delay_ms=100,
        empresa="TestEmpresa",
    )

    assert result == "success"
    assert mock_operation.call_count == 1


def test_retry_wrapper_succeeds_second_attempt(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()
    mock_operation = mocker.Mock(
        side_effect=[PlaywrightFlowError("servicio no disponible"), "success"]
    )
    mock_page = mocker.Mock()
    mock_page.wait_for_timeout = mocker.Mock()

    result = client._with_retry(
        operation=mock_operation,
        operation_name="test_op",
        max_attempts=2,
        base_delay_ms=100,
        empresa="TestEmpresa",
        page=mock_page,
    )

    assert result == "success"
    assert mock_operation.call_count == 2


def test_retry_wrapper_aborts_on_same_error(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()
    error = PlaywrightFlowError("servicio no disponible")
    mock_operation = mocker.Mock(side_effect=[error, error])
    mock_page = mocker.Mock()
    mock_page.wait_for_timeout = mocker.Mock()

    with pytest.raises(PlaywrightFlowError) as exc_info:
        client._with_retry(
            operation=mock_operation,
            operation_name="test_op",
            max_attempts=2,
            base_delay_ms=100,
            empresa="TestEmpresa",
            page=mock_page,
        )

    assert "servicio no disponible" in str(exc_info.value)
    assert mock_operation.call_count == 2


def test_retry_wrapper_aborts_on_non_transient_error(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()
    error = PlaywrightFlowError("clave o usuario incorrecto")
    mock_operation = mocker.Mock(side_effect=error)

    with pytest.raises(PlaywrightFlowError) as exc_info:
        client._with_retry(
            operation=mock_operation,
            operation_name="test_op",
            max_attempts=2,
            base_delay_ms=100,
            empresa="TestEmpresa",
        )

    assert "clave o usuario incorrecto" in str(exc_info.value)
    assert mock_operation.call_count == 1  # No reintenta
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_playwright_humanize.py::test_retry_wrapper_succeeds_first_attempt -v`
Expected: FAIL with "AttributeError: 'ArcaLpgPlaywrightClient' object has no attribute '_with_retry'"

**Step 3: Implementar método _with_retry**

```python
def _with_retry(
    self,
    operation: Callable[[], T],
    operation_name: str,
    max_attempts: int,
    base_delay_ms: int,
    empresa: str,
    page: Page | None = None,
) -> T:
    """Ejecuta una operación con reintentos para errores transitorios."""
    from typing import TypeVar
    T = TypeVar("T")

    last_error: Exception | None = None
    last_classification: ErrorClassification | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as error:
            classification = self._classify_error(error)

            logger.warning(
                "PLAYWRIGHT_OPERATION_ERROR | empresa=%s operation=%s attempt=%s/%s "
                "error_type=%s is_transient=%s message=%s",
                empresa,
                operation_name,
                attempt,
                max_attempts,
                classification.error_type,
                classification.is_transient,
                classification.message[:200],
            )

            # Si no es transitorio, fallar inmediatamente
            if not classification.is_transient:
                raise

            # Si es el último intento, fallar
            if attempt >= max_attempts:
                same_error = (
                    last_classification is not None
                    and last_classification.error_type == classification.error_type
                    and last_classification.message == classification.message
                )
                logger.error(
                    "PLAYWRIGHT_RETRY_ABORT | empresa=%s operation=%s attempts=%s "
                    "same_error=%s error_type=%s message=%s",
                    empresa,
                    operation_name,
                    attempt,
                    same_error,
                    classification.error_type,
                    classification.message[:200],
                )
                raise

            # Guardar para comparar en el próximo intento
            last_error = error
            last_classification = classification

            # Esperar antes de reintentar
            if page is not None:
                page.wait_for_timeout(base_delay_ms)
            else:
                time.sleep(base_delay_ms / 1000)

    # Nunca debería llegar aquí, pero por seguridad
    raise last_error or PlaywrightFlowError("Error desconocido en reintentos")
```

**Nota:** Agregar el import de `TypeVar` y `Callable` al inicio:

```python
from typing import Callable, TypeVar

T = TypeVar("T")
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_playwright_humanize.py -v`
Expected: PASS (11 tests)

**Step 5: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py \
        backend/tests/unit/test_playwright_humanize.py
git commit -m "feat(playwright): add retry wrapper with error classification"
```

---

## Task 6: Aplicar delays humanizados en acciones críticas

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`

**Step 1: Modificar _post_action_pause para usar humanized delays**

Reemplazar el método existente:

```python
def _post_action_pause(
    self, page: Page, delay_ms: int, action: str, empresa: str, humanize: bool = True
) -> None:
    if delay_ms <= 0:
        return
    actual_delay = self._humanized_delay(delay_ms, enabled=humanize)
    logger.debug(
        "PLAYWRIGHT_POST_ACTION_PAUSE | empresa=%s action=%s base_delay_ms=%s actual_delay_ms=%s",
        empresa, action, delay_ms, actual_delay,
    )
    page.wait_for_timeout(actual_delay)
```

**Step 2: Agregar pausas humanizadas en puntos críticos del flujo**

En `_do_login_attempt`, después de fill del CUIT (línea ~224):

```python
logger.info("PLAYWRIGHT_FILL_CUIT | empresa=%s cuit=%s", request.empresa, self._mask_cuit(request.credentials.cuit))
login_page.get_by_role("spinbutton").fill(request.credentials.cuit)
self._post_action_pause(login_page, 300, "cuit_fill", request.empresa, request.humanize_delays)
```

En `_open_consulta_recibidas`, después del primer click (línea ~591):

```python
service_page.get_by_role(
    "button", name=re.compile(r"Liquidaci[oó]n Primaria de Granos", re.IGNORECASE)
).click()
self._post_action_pause(service_page, 400, "menu_click", empresa, True)
```

En `_set_fechas`, entre los fills de fechas:

```python
input_desde.fill(fecha_desde)
self._post_action_pause(service_page, 200, "fecha_desde_fill", empresa, True)

input_hasta.wait_for(timeout=timeout_ms)
input_hasta.click()
input_hasta.fill(fecha_hasta)
self._post_action_pause(service_page, 200, "fecha_hasta_fill", empresa, True)
```

**Step 3: Verificar compilación**

Run: `cd backend && python -m compileall app/integrations/playwright/lpg_consulta_client.py -q`
Expected: Sin errores

**Step 4: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py
git commit -m "feat(playwright): apply humanized delays to critical actions"
```

---

## Task 7: Integrar reintentos en operaciones críticas

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`

**Step 1: Envolver _submit_consulta con reintentos**

El método `_submit_consulta` es propenso a errores de red. Modificar `_run_with_playwright` para usar reintentos:

```python
# En _run_with_playwright, reemplazar la llamada directa:
# self._submit_consulta(service_page, request.timeout_ms, request.empresa)

# Por:
self._with_retry(
    operation=lambda: self._submit_consulta(service_page, request.timeout_ms, request.empresa),
    operation_name="submit_consulta",
    max_attempts=request.retry_max_attempts,
    base_delay_ms=request.retry_base_delay_ms,
    empresa=request.empresa,
    page=service_page,
)
```

**Step 2: Envolver _read_results_coes con reintentos**

```python
# Reemplazar:
# headers, total_rows, coes = self._read_results_coes(...)

# Por:
headers, total_rows, coes = self._with_retry(
    operation=lambda: self._read_results_coes(
        service_page, request.timeout_ms, request.empresa
    ),
    operation_name="read_results",
    max_attempts=request.retry_max_attempts,
    base_delay_ms=request.retry_base_delay_ms,
    empresa=request.empresa,
    page=service_page,
)
```

**Step 3: Verificar compilación**

Run: `cd backend && python -m compileall app/integrations/playwright/lpg_consulta_client.py -q`
Expected: Sin errores

**Step 4: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py
git commit -m "feat(playwright): wrap critical operations with retry logic"
```

---

## Task 8: Actualizar tests de integración

**Files:**
- Modify: `backend/tests/integration/test_playwright_api.py`

**Step 1: Actualizar test_run_playwright_enqueues_job**

Agregar los nuevos parámetros esperados en el payload:

```python
assert captured["kwargs"] == {
    "extraction_job_id": body["job"]["id"],
    "fecha_desde": "01/01/2026",
    "fecha_hasta": "26/02/2026",
    "taxpayer_ids": [taxpayer_one.id, taxpayer_two.id],
    "timeout_ms": 45000,
    "type_delay_ms": 120,
    "slow_mo_ms": 0,
    "post_action_delay_ms": 0,
    "login_max_retries": 1,
    "humanize_delays": True,
    "retry_max_attempts": 2,
    "retry_base_delay_ms": 1000,
    "job_timeout": 3600,
    "result_ttl": 86400,
    "failure_ttl": 86400,
}
```

**Step 2: Run all tests**

Run: `cd backend && pytest tests/ -v --tb=short`
Expected: Algunos tests pueden fallar si la API no pasa los nuevos parámetros

**Step 3: Actualizar API si es necesario**

Si los tests fallan, modificar `backend/app/api/playwright.py` para pasar los nuevos parámetros al job.

**Step 4: Run tests again**

Run: `cd backend && pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/integration/test_playwright_api.py backend/app/api/playwright.py
git commit -m "test(playwright): update integration tests for resilience params"
```

---

## Task 9: Renombrar archivo de tests y verificación final

**Files:**
- Rename: `backend/tests/unit/test_playwright_humanize.py` → `backend/tests/unit/test_playwright_resilience.py`

**Step 1: Renombrar archivo**

```bash
git mv backend/tests/unit/test_playwright_humanize.py backend/tests/unit/test_playwright_resilience.py
```

**Step 2: Ejecutar suite completa de tests**

Run: `cd backend && pytest tests/ -v`
Expected: PASS (todos los tests)

**Step 3: Verificar que no hay errores de compilación**

Run: `cd backend && python -m compileall app tests -q`
Expected: Sin errores

**Step 4: Commit final**

```bash
git add -A
git commit -m "refactor(playwright): rename test file and final cleanup"
```

---

## Verificación Final

**Checklist:**
- [ ] Todos los tests pasan: `cd backend && pytest tests/ -v`
- [ ] Código compila: `cd backend && python -m compileall app tests -q`
- [ ] Los parámetros nuevos tienen defaults retrocompatibles
- [ ] El logging incluye información útil para debugging
