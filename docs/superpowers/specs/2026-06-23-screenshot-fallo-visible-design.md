# Feature 080 — Screenshot de fallo visible en la UI

**Fecha:** 2026-06-23
**Rama:** `feature/080-screenshot-fallo-visible` (desde `dev`)
**Estado:** Diseño aprobado

## Problema

El robot ya captura un screenshot cuando falla (login con captcha, o búsqueda del servicio),
pero hoy ese screenshot va a `/tmp/playwright_debug` dentro del container (efímero, se pierde
al recrear el container en cada deploy) y solo se loguea el path. El usuario no puede verlo.

Para casos como el captcha de Erlina, ver la pantalla real que recibió el robot es la forma
más directa de entender qué pasó. La feature 077 ya muestra el detalle del job en un drawer
(`JobDetailDrawer`); falta sumar la imagen.

## Solución

Persistir el screenshot del fallo en la DB (base64, patrón `pdf_cache`), exponerlo por un
endpoint con auth, y mostrarlo en el `JobDetailDrawer` existente. Una purga automática borra
los screenshots con más de N días (default 3) para que los blobs no se acumulen.

## Modelo de datos

Nueva tabla `job_screenshot` (espejo de `pdf_cache`, imagen aislada para no inflar
`extraction_job`):

```
id              INTEGER PK
extraction_job_id INTEGER FK → extraction_job (index)
taxpayer_id     INTEGER FK → taxpayer
image_base64    TEXT NOT NULL
fase            VARCHAR(40) NULL   # fase donde se capturó (LOGIN_START, SEARCH_SERVICE, ...)
created_at      DATETIME NOT NULL (default now Cordoba)
```

Un job puede tener 0 o 1 screenshot (se crea uno por fallo capturado). La tabla 1-a-muchos
mantiene `extraction_job` liviano: las queries de jobs no cargan el blob (~400KB en base64).

## Propagación del screenshot (cliente → worker → DB)

El screenshot se captura dentro del cliente Playwright (`_log_login_diagnostics` /
`_log_search_service_diagnostics`), pero quien persiste el job es el worker. Los bytes
viajan por el mismo canal que la info de fallo existente: `TaxpayerPipelineResult`.

1. **Cliente** (`lpg_consulta_client.py`): las funciones de diagnóstico, además de loguear,
   devuelven los bytes PNG del screenshot (`bytes | None`). Hoy son void; pasan a retornar
   los bytes. El flujo de fallo retiene esos bytes.
2. **Pipeline** (`lpg_playwright_pipeline.py`): `TaxpayerPipelineResult` suma
   `failure_screenshot_png: bytes | None = None`. El handler de error lo llena desde el
   cliente (igual que ya llena `failure_phase`).
3. **Worker** (`playwright_jobs.py`): al persistir un job fallido, si
   `result.failure_screenshot_png` no es None, crea un `job_screenshot` con
   `base64.b64encode(bytes).decode()` y la fase.

> No se elimina la escritura a `/tmp` ni el log del path (sirve para debug de bajo nivel);
> se ADICIONA la persistencia en DB.

## Endpoint

`GET /api/jobs/<int:job_id>/screenshot` con `@require_auth`:
- Busca el `job_screenshot` del job. Si existe → `send_file(io.BytesIO(base64.b64decode(image_base64)), mimetype="image/png")`.
- Si no existe → 404 `{"error": "..."}`.
- Mismo patrón que `download_coe_pdf` en `coes.py`.

El serializer de `GET /api/jobs/<id>` suma `tiene_screenshot: bool` (existe un job_screenshot
para ese job) — sin cargar el blob en el JSON.

## Frontend

En `JobDetailDrawer` (componente existente), agregar una sección "Captura de pantalla" que
se renderiza SOLO si `job.tiene_screenshot` es true:
- Un `<img src="/api/jobs/<id>/screenshot">` (con el manejo de auth que use el proyecto para
  imágenes; si el endpoint requiere header Authorization, usar el patrón de fetch→blob→objectURL
  igual que se sirve el PDF, o un `<img>` directo si la sesión va por cookie — verificar en
  implementación cómo se autentican los assets).
- Tipo `Job` (en `api/jobs.ts`) suma `tiene_screenshot: boolean`.

> En implementación, verificar cómo el frontend autentica requests de assets binarios: si
> `fetchWithAuth` agrega un header Bearer, un `<img src>` plano NO lo lleva → habría que
> fetchear el blob y crear un objectURL. Resolver según el patrón real del proyecto (mirar
> cómo se muestra/descarga el PDF del COE).

## Limpieza automática

`purge_old_screenshots(max_age_days: int) -> int` en un servicio nuevo
(`services/screenshot_service.py`): borra registros `job_screenshot` con
`created_at < now - max_age_days`. Devuelve la cantidad borrada.

Se cablea en el loop de `worker_scheduler.py`, junto a `reconcile_stale_jobs` que ya corre
periódicamente. Retención configurable vía `SCREENSHOT_RETENTION_DAYS` (default 3) en `config.py`.

## Testing

### Backend
- Crear `job_screenshot` al persistir un job fallido con `failure_screenshot_png` no None.
- No crear si `failure_screenshot_png` es None.
- Endpoint: 200 + PNG cuando existe; 404 cuando no; 401 sin auth.
- Serializer de job incluye `tiene_screenshot` (true/false según corresponda).
- `purge_old_screenshots`: borra los más viejos que el umbral, conserva los recientes,
  devuelve la cantidad borrada.

### Frontend
`tsc --noEmit` + `npm run build`. La sección de imagen se valida visualmente.

## Archivos afectados (estimado)

- `backend/app/models/job_screenshot.py` (nuevo) + `models/__init__.py`
- `backend/migrations/versions/*` — tabla `job_screenshot`
- `backend/app/services/lpg_playwright_pipeline.py` — campo `failure_screenshot_png`
- `backend/app/integrations/playwright/lpg_consulta_client.py` — devolver bytes del screenshot
- `backend/app/workers/playwright_jobs.py` — persistir `job_screenshot`
- `backend/app/services/screenshot_service.py` (nuevo) — `purge_old_screenshots`
- `backend/app/workers/worker_scheduler.py` — cablear la purga
- `backend/app/api/jobs.py` — endpoint `/screenshot` + `tiene_screenshot` en serializer
- `backend/app/config.py` — `SCREENSHOT_RETENTION_DAYS`
- `frontend/src/api/jobs.ts` — `tiene_screenshot` en `Job`
- `frontend/src/components/dashboard/JobDetailDrawer.tsx` — sección imagen
- tests correspondientes

## Fuera de alcance

- Resolver el captcha automáticamente (descartado: frágil, contra términos de AFIP).
- Capturar screenshots en fases nuevas (se usan las 2 capturas que ya existen).
- Historial de múltiples screenshots por job (1 por fallo alcanza).
