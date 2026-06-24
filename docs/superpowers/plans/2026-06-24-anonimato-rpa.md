# Anonimato del RPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reducir el riesgo de captcha de AFIP haciendo que el RPA parezca un navegador normal (Chromium headed real bajo Xvfb + user-agent coherente) y repartiendo las extracciones nocturnas en una ventana 03:00–06:00 con jitter aleatorio.

**Architecture:** Tres cambios de backend desacoplados. (1) Config `PLAYWRIGHT_HEADLESS` enchufada en la cadena del worker para permitir modo headed. (2) User-agent construido en runtime desde la versión real del browser. (3) Jitter de encolado con `queue.enqueue_in` + worker RQ con scheduler embebido. La infra (Xvfb en Dockerfile + `xvfb-run` en el command del worker) se aplica en el deploy.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, RQ (>=1.16,<2), Playwright (Chromium), pytest, Docker, Xvfb.

## Global Constraints

- **Invariante de concurrencia:** máximo 1 extracción Playwright concurrente. El worker único + jitter lo garantizan. No paralelizar.
- **No romper local/CI:** sin Xvfb disponible, todo debe seguir corriendo headless. Los defaults de config son `headless=True`.
- **Fallback obligatorio:** si el launch headed falla, degradar a headless con log warning, nunca romper la extracción.
- **Conventional commits**, sin atribución AI (regla del proyecto).
- **Timezone** America/Argentina/Cordoba para timestamps (ya existente vía `time_utils`).
- Tests: pytest, fixtures en `backend/tests/conftest.py`. Correr desde `backend/`.

---

### Task 1: Config `PLAYWRIGHT_HEADLESS` y enchufe en el worker

**Files:**
- Modify: `backend/app/config.py` (agregar la var junto a las otras `PLAYWRIGHT_*`)
- Modify: `backend/app/workers/playwright_jobs.py:518` (reemplazar literal `headless=True`)
- Test: `backend/tests/unit/test_playwright_headless_config.py`

**Interfaces:**
- Produces: `Config.PLAYWRIGHT_HEADLESS: bool` (default `True`), leído vía `current_app.config["PLAYWRIGHT_HEADLESS"]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_playwright_headless_config.py
from __future__ import annotations

import importlib


def test_default_headless_es_true(monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_HEADLESS", raising=False)
    import app.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.Config.PLAYWRIGHT_HEADLESS is True


def test_headless_false_por_env(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "false")
    import app.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.Config.PLAYWRIGHT_HEADLESS is False


def test_headless_true_por_env(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "true")
    import app.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.Config.PLAYWRIGHT_HEADLESS is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/unit/test_playwright_headless_config.py -q`
Expected: FAIL con `AttributeError: ... PLAYWRIGHT_HEADLESS`

- [ ] **Step 3: Add config var**

En `backend/app/config.py`, junto a las otras `PLAYWRIGHT_*` (después de `PLAYWRIGHT_NAV_LOGIN_TIMEOUT_MS`):

```python
    PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").strip().lower() not in ("false", "0", "no")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/unit/test_playwright_headless_config.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Enchufar en el worker**

En `backend/app/workers/playwright_jobs.py`, dentro de `run_playwright_pipeline_job` (que ya corre dentro de `with app.app_context()`), reemplazar la línea ~518:

```python
                headless=True,
```

por:

```python
                headless=current_app.config["PLAYWRIGHT_HEADLESS"],
```

Verificar que `current_app` está importado en el archivo (`from flask import current_app`); si no, agregar el import.

- [ ] **Step 6: Compile + suite del worker**

Run: `cd backend && python3 -m compileall app/workers/playwright_jobs.py -q && python3 -m pytest tests/unit/test_worker_scheduler_hook.py tests/unit/test_playwright_headless_config.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/workers/playwright_jobs.py backend/tests/unit/test_playwright_headless_config.py
git commit -m "feat(playwright): config PLAYWRIGHT_HEADLESS para permitir modo headed"
```

---

### Task 2: User-agent coherente Linux desde la versión real del browser

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py` (método `_run_with_playwright`, ~líneas 350-360; constante `DEFAULT_USER_AGENT` ~176)
- Test: `backend/tests/unit/test_lpg_user_agent.py`

**Interfaces:**
- Consumes: `Config.PLAYWRIGHT_HEADLESS` (no directamente; el headless le llega vía `request.headless`).
- Produces: método `_build_user_agent(self, browser_version: str) -> str` en `ArcaLpgPlaywrightClient` que devuelve un UA Linux con la versión dada.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_lpg_user_agent.py
from __future__ import annotations


def test_user_agent_es_linux_con_version_real():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()
    ua = client._build_user_agent("120.0.6099.109")

    assert "X11; Linux x86_64" in ua
    assert "Windows" not in ua
    assert "Chrome/120.0.6099.109" in ua
    assert ua.startswith("Mozilla/5.0")


def test_user_agent_normaliza_version_corta():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()
    # browser.version puede venir como "120.0.6099.109" o solo mayor; aceptar ambos
    ua = client._build_user_agent("131.0.0.0")
    assert "Chrome/131.0.0.0" in ua
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/unit/test_lpg_user_agent.py -q`
Expected: FAIL con `AttributeError: ... _build_user_agent`

- [ ] **Step 3: Implementar `_build_user_agent`**

En `backend/app/integrations/playwright/lpg_consulta_client.py`, agregar el método a la clase `ArcaLpgPlaywrightClient`:

```python
    def _build_user_agent(self, browser_version: str) -> str:
        """Construye un UA coherente con el SO real (Linux) y la versión
        real de Chromium en runtime, para evitar la contradicción
        SO-declarado vs SO-real que delata al robot."""
        return (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{browser_version} Safari/537.36"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/unit/test_lpg_user_agent.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Usar el UA dinámico en el launch**

En `_run_with_playwright`, después de `browser = playwright.chromium.launch(...)` y antes de `context = browser.new_context(...)`, construir el UA desde la versión real y pasarlo:

```python
        browser = playwright.chromium.launch(
            headless=request.headless,
            slow_mo=request.slow_mo_ms,
            args=self.BROWSER_ARGS,
        )
        user_agent = self._build_user_agent(browser.version)
        context = browser.new_context(
            user_agent=user_agent,
            viewport=self.DEFAULT_VIEWPORT,
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
```

Eliminar la constante `DEFAULT_USER_AGENT` (ya no se usa) o dejarla solo si algún otro punto la referencia — verificar con `rg "DEFAULT_USER_AGENT" backend/` y quitar si queda huérfana.

- [ ] **Step 6: Verificar que no quedó referencia huérfana + compile**

Run: `cd backend && rg -n "DEFAULT_USER_AGENT" app/ ; python3 -m compileall app/integrations/playwright/lpg_consulta_client.py -q && echo OK`
Expected: sin referencias huérfanas, `OK`

- [ ] **Step 7: Run suite del cliente Playwright**

Run: `cd backend && python3 -m pytest tests/unit/test_lpg_user_agent.py tests/unit/test_lpg_search_service_debounce.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py backend/tests/unit/test_lpg_user_agent.py
git commit -m "feat(playwright): user-agent coherente Linux desde la version real del browser"
```

---

### Task 3: Fallback headed → headless

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py` (`_run_with_playwright`, bloque de launch)
- Test: `backend/tests/unit/test_lpg_headed_fallback.py`

**Interfaces:**
- Consumes: `request.headless` (bool).
- Produces: comportamiento — si `launch(headless=False)` lanza excepción, reintenta `launch(headless=True)` y loguea warning.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_lpg_headed_fallback.py
from __future__ import annotations

import pytest


def test_launch_headed_cae_a_headless_si_falla(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()

    chromium = mocker.MagicMock()
    browser_ok = mocker.MagicMock()
    browser_ok.version = "120.0.0.0"
    # Primera llamada (headed) revienta; segunda (headless) OK.
    chromium.launch.side_effect = [RuntimeError("Xvfb no disponible"), browser_ok]

    result = client._launch_browser_with_fallback(
        chromium, headless=False, slow_mo_ms=0
    )

    assert result is browser_ok
    assert chromium.launch.call_count == 2
    # Segunda llamada fue headless=True
    assert chromium.launch.call_args_list[1].kwargs["headless"] is True


def test_launch_headed_ok_no_reintenta(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()
    chromium = mocker.MagicMock()
    browser_ok = mocker.MagicMock()
    chromium.launch.return_value = browser_ok

    result = client._launch_browser_with_fallback(
        chromium, headless=False, slow_mo_ms=0
    )

    assert result is browser_ok
    assert chromium.launch.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/unit/test_lpg_headed_fallback.py -q`
Expected: FAIL con `AttributeError: ... _launch_browser_with_fallback`

- [ ] **Step 3: Implementar el helper**

En `ArcaLpgPlaywrightClient`:

```python
    def _launch_browser_with_fallback(self, chromium, *, headless: bool, slow_mo_ms: int):
        """Lanza el browser. Si headed falla (ej. Xvfb ausente), degrada a
        headless con warning — headed es mejora de anonimato, no requisito."""
        try:
            return chromium.launch(
                headless=headless, slow_mo=slow_mo_ms, args=self.BROWSER_ARGS
            )
        except Exception:
            if headless:
                raise
            logger.warning(
                "PLAYWRIGHT_HEADED_FALLBACK | headed falló, reintentando headless",
                exc_info=True,
            )
            return chromium.launch(
                headless=True, slow_mo=slow_mo_ms, args=self.BROWSER_ARGS
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/unit/test_lpg_headed_fallback.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Usar el helper en `_run_with_playwright`**

Reemplazar el bloque de launch directo por la llamada al helper:

```python
        browser = self._launch_browser_with_fallback(
            playwright.chromium,
            headless=request.headless,
            slow_mo_ms=request.slow_mo_ms,
        )
        user_agent = self._build_user_agent(browser.version)
        context = browser.new_context(
            user_agent=user_agent,
            viewport=self.DEFAULT_VIEWPORT,
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
```

- [ ] **Step 6: Compile + suite del cliente**

Run: `cd backend && python3 -m compileall app/integrations/playwright/lpg_consulta_client.py -q && python3 -m pytest tests/unit/test_lpg_headed_fallback.py tests/unit/test_lpg_user_agent.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py backend/tests/unit/test_lpg_headed_fallback.py
git commit -m "feat(playwright): fallback headed a headless si el display virtual falla"
```

---

### Task 4: Worker RQ con scheduler embebido

**Files:**
- Modify: `backend/worker.py:25` (`with_scheduler=False` → `True`)
- Test: `backend/tests/unit/test_worker_with_scheduler.py`

**Interfaces:**
- Produces: el worker procesa scheduled jobs (necesario para `enqueue_in` en Task 5).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_worker_with_scheduler.py
from __future__ import annotations

import worker as worker_mod


def test_worker_arranca_con_scheduler(monkeypatch):
    captured = {}

    class FakeWorker:
        def __init__(self, queues, connection):
            captured["queues"] = queues

        def work(self, with_scheduler=False):
            captured["with_scheduler"] = with_scheduler

    monkeypatch.setattr(worker_mod, "Worker", FakeWorker)
    monkeypatch.setattr(worker_mod, "Redis", type("R", (), {"from_url": staticmethod(lambda url: object())}))
    monkeypatch.setattr(worker_mod, "create_app", lambda: __import__("app").create_app())

    worker_mod.main()

    assert captured["with_scheduler"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/unit/test_worker_with_scheduler.py -q`
Expected: FAIL (`assert False is True`)

- [ ] **Step 3: Cambiar el arranque del worker**

En `backend/worker.py`, línea 25:

```python
        worker.work(with_scheduler=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/unit/test_worker_with_scheduler.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/worker.py backend/tests/unit/test_worker_with_scheduler.py
git commit -m "feat(worker): habilitar scheduler embebido de RQ para jobs diferidos"
```

---

### Task 5: Jitter en el encolado del scheduler

**Files:**
- Modify: `backend/app/config.py` (agregar `SCHEDULER_JITTER_WINDOW_SECONDS`)
- Modify: `backend/app/services/scheduler_service.py` (`_disparar_extraccion`, imports)
- Test: `backend/tests/unit/test_scheduler_jitter.py`

**Interfaces:**
- Consumes: `Config.SCHEDULER_JITTER_WINDOW_SECONDS: int` (default 10800).
- Produces: `_disparar_extraccion` encola con `queue.enqueue_in(timedelta(seconds=delay), ...)` donde `delay ∈ [0, JITTER_WINDOW]`, y persiste `jitter_delay_seconds` en el payload.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_scheduler_jitter.py
from __future__ import annotations

from datetime import timedelta


def _create_taxpayer(db, Taxpayer):
    tp = Taxpayer(
        cuit="20111111199",
        empresa="Jitter SA",
        cuit_representado="30711165378",
        activo=True,
        scheduler_activo=True,
        scheduler_dias_semana="lun,mar,mie,jue,vie,sab,dom",
        scheduler_hora_local="03:00",
        scheduler_dias_extraccion=90,
        playwright_enabled=True,
        clave_fiscal_encrypted="x",
    )
    db.session.add(tp)
    db.session.commit()
    return tp


def test_disparar_usa_enqueue_in_con_delay_en_ventana(app, mocker):
    with app.app_context():
        from app.extensions import db
        from app.models import Taxpayer
        from app.services import scheduler_service

        app.config["SCHEDULER_JITTER_WINDOW_SECONDS"] = 10800
        tp = _create_taxpayer(db, Taxpayer)

        fake_queue = mocker.MagicMock()
        fake_rq_job = mocker.MagicMock()
        fake_rq_job.id = "rq-123"
        fake_queue.name = "playwright"
        fake_queue.enqueue_in.return_value = fake_rq_job
        mocker.patch.object(scheduler_service, "get_queue", return_value=fake_queue)
        # delay determinístico
        mocker.patch.object(scheduler_service.random, "randint", return_value=4242)

        job = scheduler_service._disparar_extraccion(tp)

        fake_queue.enqueue_in.assert_called_once()
        delta_arg = fake_queue.enqueue_in.call_args.args[0]
        assert delta_arg == timedelta(seconds=4242)
        assert job.payload["jitter_delay_seconds"] == 4242


def test_delay_nunca_excede_la_ventana(app, mocker):
    with app.app_context():
        from app.extensions import db
        from app.models import Taxpayer
        from app.services import scheduler_service

        app.config["SCHEDULER_JITTER_WINDOW_SECONDS"] = 100
        tp = _create_taxpayer(db, Taxpayer)

        fake_queue = mocker.MagicMock()
        fake_queue.name = "playwright"
        fake_queue.enqueue_in.return_value = mocker.MagicMock(id="x")
        mocker.patch.object(scheduler_service, "get_queue", return_value=fake_queue)
        spy = mocker.spy(scheduler_service.random, "randint")

        scheduler_service._disparar_extraccion(tp)

        # randint llamado con (0, 100)
        assert spy.call_args.args == (0, 100)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/unit/test_scheduler_jitter.py -q`
Expected: FAIL (`enqueue_in` no llamado / `random` no importado en el módulo)

- [ ] **Step 3: Agregar config**

En `backend/app/config.py`, junto a `SCHEDULER`/`STALE`:

```python
    SCHEDULER_JITTER_WINDOW_SECONDS = int(os.getenv("SCHEDULER_JITTER_WINDOW_SECONDS", "10800"))
```

- [ ] **Step 4: Modificar `_disparar_extraccion`**

En `backend/app/services/scheduler_service.py`:

Agregar import al tope (junto a los `import` del stdlib):

```python
import random
```

En `_disparar_extraccion`, reemplazar el bloque de enqueue. Hoy:

```python
    queue = get_queue(SCHEDULER_QUEUE_NAME)
    rq_job = queue.enqueue(
        run_playwright_pipeline_job,
        extraction_job_id=job.id,
        **enqueue_kwargs,
    )
```

por:

```python
    queue = get_queue(SCHEDULER_QUEUE_NAME)
    jitter_window = current_app.config["SCHEDULER_JITTER_WINDOW_SECONDS"]
    delay_segundos = random.randint(0, jitter_window)
    rq_job = queue.enqueue_in(
        timedelta(seconds=delay_segundos),
        run_playwright_pipeline_job,
        extraction_job_id=job.id,
        **enqueue_kwargs,
    )
```

Y en el bloque que arma el payload final, agregar `jitter_delay_seconds`:

```python
    job.payload = {
        **(job.payload or {}),
        "queue_name": queue.name,
        "rq_job_id": rq_job.id,
        "jitter_delay_seconds": delay_segundos,
    }
    db.session.commit()
```

Y agregar `delay_segundos` al log `SCHEDULER_DISPARO`:

```python
    logger.info(
        "SCHEDULER_DISPARO | taxpayer_id=%s job_id=%s operation=%s queue=%s rq_job_id=%s jitter_delay_s=%s",
        taxpayer.id,
        job.id,
        SCHEDULER_OPERATION,
        queue.name,
        rq_job.id,
        delay_segundos,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/unit/test_scheduler_jitter.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Suite completa del scheduler (sin regresión)**

Run: `cd backend && python3 -m pytest tests/unit/test_scheduler_service.py tests/unit/test_scheduler_jitter.py tests/unit/test_scheduler_auto_block.py tests/unit/test_worker_scheduler_loop.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/services/scheduler_service.py backend/tests/unit/test_scheduler_jitter.py
git commit -m "feat(scheduler): jitter aleatorio en el encolado para repartir extracciones 03-06h"
```

---

### Task 6: Infra Xvfb en el Dockerfile

**Files:**
- Modify: `backend/Dockerfile`

**Interfaces:**
- Produces: imagen del backend con `xvfb` y `xauth` instalados (usados por el command del worker en prod).

- [ ] **Step 1: Leer el Dockerfile actual**

Run: `cat backend/Dockerfile`
Identificar el bloque `RUN` que instala dependencias del sistema / playwright.

- [ ] **Step 2: Agregar xvfb + xauth**

En `backend/Dockerfile`, agregar (preferentemente cerca del `playwright install --with-deps`, en un `RUN apt-get` propio para no invalidar otras capas):

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Verificar sintaxis del Dockerfile**

Run: `cd backend && docker build --target deps -f Dockerfile . 2>/dev/null || echo "build local opcional — si Docker no está disponible, validar el diff manualmente"`
Expected: build OK, o validación manual del diff si no hay Docker local.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile
git commit -m "build(worker): instalar xvfb y xauth para Chromium headed"
```

---

### Task 7: Documentar variables de entorno

**Files:**
- Modify: `.env.example` (agregar las 2 vars nuevas)

**Interfaces:**
- Produces: documentación de `PLAYWRIGHT_HEADLESS` y `SCHEDULER_JITTER_WINDOW_SECONDS`.

- [ ] **Step 1: Agregar al `.env.example`**

En la sección de Playwright / scheduler:

```
# Playwright: false = browser headed bajo Xvfb (mejor anonimato, ~2x RAM). Default true.
PLAYWRIGHT_HEADLESS=true
# Ventana de jitter para repartir las extracciones del scheduler (segundos). Default 10800 = 3h (03:00-06:00).
SCHEDULER_JITTER_WINDOW_SECONDS=10800
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs(env): documentar PLAYWRIGHT_HEADLESS y SCHEDULER_JITTER_WINDOW_SECONDS"
```

---

### Task 8: Suite completa + verificación final

**Files:** ninguno (verificación)

- [ ] **Step 1: Correr toda la suite backend**

Run: `cd backend && python3 -m pytest -q`
Expected: todos PASS (incluye los nuevos tests de las tasks 1-5).

- [ ] **Step 2: Compile check global**

Run: `cd backend && python3 -m compileall app worker.py worker_scheduler.py -q && echo OK`
Expected: `OK`

- [ ] **Step 3: Revisar que el data flow quede coherente**

Verificar manualmente: `_disparar_extraccion` usa `enqueue_in` (Task 5), `worker.py` tiene `with_scheduler=True` (Task 4), el job lee `PLAYWRIGHT_HEADLESS` (Task 1). Sin estos tres juntos, el jitter no ejecuta o el headed no aplica.

---

## Pasos de deploy (NO son tasks de código — se aplican en el VPS)

Estos cambios viven solo en el VPS (`docker-compose.prod.yml` no está versionado). Se aplican durante el deploy, después de mergear a main:

1. En `docker-compose.prod.yml`, servicio `worker`: cambiar el `command` a
   `xvfb-run -a --server-args="-screen 0 1366x768x24" python worker.py`
2. Agregar al entorno del servicio `worker` (y `scheduler_worker` si aplica): `PLAYWRIGHT_HEADLESS=false`.
3. (Opcional) `SCHEDULER_JITTER_WINDOW_SECONDS` en el servicio `scheduler_worker` si se quiere distinta de 3h.
4. Deploy normal (`deploy.sh`) — rebuildeará la imagen con xvfb/xauth (Task 6) y recreará los containers.
5. **Verificación post-deploy primera noche:** monitorear `docker stats` durante la ventana 03:00–06:00 (RSS del worker < 800 MB, swap estable) y confirmar en logs `SCHEDULER_DISPARO | ... jitter_delay_s=N` con delays variados.

## Self-review

- **Spec coverage:** Punto 2 headed → Tasks 1+6+deploy; UA coherente → Task 2; fallback → Task 3; Punto 3 jitter → Task 5; RQ scheduler obligatorio → Task 4; config docs → Task 7; invariante de concurrencia → respetado (worker único, sin paralelización). ✓
- **Dedup/stale:** el spec aclara que no se afectan; no requieren cambio de código (jobs scheduled no están `running`). Sin task. ✓
- **Placeholders:** ninguno; todo el código está completo. ✓
- **Type consistency:** `_build_user_agent(version) -> str`, `_launch_browser_with_fallback(chromium, *, headless, slow_mo_ms)`, `PLAYWRIGHT_HEADLESS: bool`, `SCHEDULER_JITTER_WINDOW_SECONDS: int`, payload key `jitter_delay_seconds` — consistentes entre tasks. ✓
