# Diseño: Mejora de anonimato del RPA (082)

**Fecha:** 2026-06-24
**Rama:** feature/082-anonimato-rpa
**Objetivo:** Reducir el riesgo de que AFIP active el captcha anti-bot sobre los clientes, evitando que más clientes caigan en el escenario que sufrió Erlina. Perfil **conservador**: parecer un navegador normal y no disparar alarmas, sin técnicas que AFIP pueda leer como evasión deliberada.

## Contexto

AFIP pide captcha por una combinación de señales de riesgo. En el caso Erlina se confirmó: 5 días de `AUTH_FAILED` (clave vieja) → AFIP marcó fuerza bruta → activó captcha. Pero el patrón general que delata al robot tiene tres señales que aún no atacamos:

1. **Browser headless** — hoy se usa `chromium_headless_shell` (`headless=True`), el binario más detectable.
2. **User-agent incoherente** — el UA declara `Windows NT 10.0 ... Chrome/120` pero el proceso corre sobre Linux con Chromium 1223. La contradicción SO-declarado vs SO-real es detectable.
3. **Ráfaga sincronizada** — a las 03:00 exactas el tick encola los 63 jobs de golpe; el worker único los procesa seguidos sin pausa (~45s c/u, ~47 min total). 63 logins consecutivos desde la misma IP es señal de bot.

Ya resuelto en features previas (no es parte de este diseño): el embudo `AUTH_FAILED → captcha` se previene con el auto-bloqueo de la feature 079.

## Alcance

Dos cambios, ambos en el backend:

- **Punto 2 — Browser headed real bajo Xvfb** + user-agent coherente.
- **Punto 3 — Jitter en el encolado**: repartir los 63 jobs en la ventana 03:00–06:00 con delay aleatorio por cliente.

Fuera de alcance: proxy residencial / cambio de IP (se evaluará después, con evidencia de si estos cambios gratuitos ya bastan); `playwright-stealth`; paralelización de workers (explícitamente no deseada).

## Invariante de recursos (medido en el VPS)

VPS: 3.7 GB RAM, 2 vCPU, 2 GB swap (≈600 MB ya en uso en reposo), ~2.2 GB libres.

Consumo de Chromium medido en el container worker:
- Headless: **341 MB** RSS.
- Headed bajo Xvfb: **~685 MB** RSS + ~30 MB del proceso Xvfb ≈ **715 MB**.

El modo headed cuesta ~2x RAM. Es viable **sin upgrade** porque hay **una sola extracción concurrente** (worker RQ con concurrencia 1 + jitter que espacia los jobs). Nunca hay 2 Chromium a la vez → pico = 1 × 715 MB, entra en los 2.2 GB libres.

**INVARIANTE (no opcional):** máximo 1 extracción Playwright concurrente. El jitter y el worker único garantizan esto; es lo que hace el headed viable sin upgrade. Si en el futuro se quisiera paralelizar, se requiere upgrade de RAM primero.

## Punto 2 — Browser headed bajo Xvfb

### Infraestructura (Dockerfile del worker)

Agregar al Dockerfile los paquetes del SO necesarios para correr un display virtual:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
```

Los binarios de Chromium (completo + headless_shell) ya están instalados vía `playwright install --with-deps chromium`. No se instala nada nuevo de Playwright.

### Arranque del display virtual

El comando del worker (`docker-compose.prod.yml`, servicio `worker`) se envuelve con `xvfb-run`:

```
xvfb-run -a --server-args="-screen 0 1366x768x24" python worker.py
```

`xvfb-run -a` elige un display libre automáticamente y lo limpia al salir. La resolución coincide con `DEFAULT_VIEWPORT` (1366x768).

Nota operativa: `docker-compose.prod.yml` y el Dockerfile de prod viven en el VPS. El Dockerfile sí está versionado (`backend/Dockerfile`); el compose de prod no. El cambio del Dockerfile va en el repo; el ajuste del `command` del servicio worker va aplicado en el VPS durante el deploy.

### Cambio en el cliente Playwright

`app/integrations/playwright/lpg_consulta_client.py`:

1. **Launch headed por defecto.** Hoy `headless` está **hardcodeado a `True`** en la cadena: `app/workers/playwright_jobs.py:518` lo pasa fijo, y los defaults del pipeline (`lpg_playwright_pipeline.py`) son `True`. No existe env var para esto. Cambio: agregar `PLAYWRIGHT_HEADLESS` a `app/config.py` (default `True` para no romper local/CI), y enchufarla en el punto donde el worker arma el request (`playwright_jobs.py:518`) en lugar del literal `True`. En prod se setea `PLAYWRIGHT_HEADLESS=false`. CI/local sin Xvfb quedan headless por el default.

2. **User-agent coherente.** Reemplazar el UA hardcodeado de Windows por uno que refleje Linux + la versión real de Chromium. Construir el UA a partir de la versión del browser en runtime (`browser.version`) en lugar de hardcodear, para que no vuelva a desincronizarse en futuros updates de Playwright. UA objetivo:
   `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/<version-real> Safari/537.36`

3. **Mantener** lo que ya está bien: `locale=es-AR`, `timezone_id` argentino, `viewport`, `WEBDRIVER_HIDE_SCRIPT`, `--disable-blink-features=AutomationControlled`.

### Fallback

Si el browser headed falla al lanzar (ej. Xvfb no disponible en algún entorno), el código debe degradar a headless con un log de warning, no romper la extracción. La extracción headless sigue siendo funcional; headed es una mejora de anonimato, no un requisito de funcionamiento.

## Punto 3 — Jitter en el encolado

### Cambio en el scheduler

`app/services/scheduler_service.py`, función `_disparar_extraccion`:

Hoy:
```python
rq_job = queue.enqueue(run_playwright_pipeline_job, ...)
```

Nuevo: encolar con un delay aleatorio dentro de la ventana configurable.

```python
delay_segundos = random.randint(0, JITTER_WINDOW_SECONDS)
rq_job = queue.enqueue_in(timedelta(seconds=delay_segundos), run_playwright_pipeline_job, ...)
```

- `JITTER_WINDOW_SECONDS` configurable (env var, default 10800 = 3h → ventana 03:00–06:00).
- `random` del stdlib (no hace falta criptográfico; es jitter de timing). Semilla por defecto del sistema.
- El delay se registra en el log `SCHEDULER_DISPARO` y en el payload del job para trazabilidad.

### Interacción con RQ scheduler (cambio obligatorio)

`enqueue_in` deja el job en el registro de *scheduled jobs*; alguien debe moverlo a la cola activa cuando vence su delay. Hoy `worker.py:25` corre `worker.work(with_scheduler=False)` → **los jobs diferidos nunca se ejecutarían.** Este es el corazón del punto 3.

Cambio concreto: `worker.py` pasa a `worker.work(with_scheduler=True)`. La versión `rq>=1.16,<2` ya soporta el scheduler embebido en el worker (no requiere proceso aparte ni `rq-scheduler`). Con un solo worker y `with_scheduler=True`, ese mismo proceso mueve los scheduled jobs vencidos a la cola y los procesa (sigue siendo 1 concurrencia, respeta el invariante).

### Interacción con el dedup window

`DEDUP_WINDOW_SECONDS` (1h) evita re-disparo si `scheduler_ultimo_ok` es reciente. Con jitter, un job puede ejecutarse hasta 3h después de encolarse. El dedup se evalúa **al encolar** (en el tick), no al ejecutar, así que sigue correcto: el tick de las 03:00 evalúa una vez y encola con delay. No hay doble disparo porque el tick de las 03:01 no vuelve a matchear la misma hora `03:00`.

### Reconciliador de jobs stale

`reconcile_stale_jobs` marca como failed los jobs `running` sin actividad por > `STALE_JOB_TIMEOUT_SECONDS` (30 min). Esto opera sobre jobs **en ejecución**, no encolados/diferidos, así que el jitter no lo afecta: un job diferido está en estado scheduled, no running. Confirmar en implementación que un job scheduled (esperando su delay) no se cuenta como stale.

## Data flow

```
03:00 tick_scheduler()
  └─ por cada taxpayer que matchea (día + hora 03:00):
       ├─ evalúa dedup (ultimo_ok < 1h → skip)
       ├─ crea ExtractionJob(status=pending)
       └─ queue.enqueue_in(random 0..3h, run_playwright_pipeline_job)
             └─ RQ scheduler mueve el job a la cola activa al vencer su delay
                   └─ worker único (concurrencia 1) lo toma
                         └─ xvfb-run → Chromium headed → login AFIP → extracción
```

## Testing

- **Punto 3 (unit):** `_disparar_extraccion` usa `enqueue_in` con delay en `[0, JITTER_WINDOW_SECONDS]`; mockear `queue.enqueue_in` y `random` para verificar el rango y que el delay se persiste en el payload. Regresión: el delay nunca excede la ventana.
- **Punto 2 (unit):** el cliente construye el UA con la versión real del browser (no hardcoded Windows); el launch usa `headless` según config; fallback a headless si headed lanza excepción.
- **Manual/staging:** una corrida headed bajo Xvfb que llegue al login (sin necesariamente extraer) confirma que el browser arranca y renderiza. Verificar RSS < 800 MB durante la corrida.

## Riesgos y mitigaciones

- **RAM:** mitigado por el invariante de 1 concurrencia. Monitorear swap durante la primera noche post-deploy.
- **Xvfb no arranca:** fallback a headless + log warning.
- **RQ no procesa scheduled jobs:** verificar `--with-scheduler` en implementación; sin esto los jobs diferidos no se ejecutarían (riesgo alto, es el corazón del punto 3).
- **No medible de inmediato:** que esto reduzca el captcha solo se confirma con el tiempo (ausencia de nuevos `AUTH_FAILED`/captcha en semanas). Es prevención, no fix verificable en el acto.

## Criterio de éxito

- Extracciones nocturnas corren con browser headed real, UA coherente Linux, repartidas en 03:00–06:00.
- Sin regresión funcional: la tasa de éxito de extracciones se mantiene o mejora.
- RAM/swap del VPS estable durante la ventana nocturna (1 browser a la vez).
- A mediano plazo: ningún cliente nuevo cae en captcha.
