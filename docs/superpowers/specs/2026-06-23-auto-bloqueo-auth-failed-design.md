# Feature 079 — Auto-bloqueo del scheduler ante clave incorrecta

**Fecha:** 2026-06-23
**Rama:** `feature/079-auto-bloqueo-auth-failed` (desde `dev`)
**Estado:** Diseño aprobado

## Problema (causa raíz investigada)

El cliente Erlina S.A.S. (taxpayer 30) cayó en un escenario de CAPTCHA de AFIP que rompe
la extracción. La investigación con datos de producción reveló la cadena real:

1. ~10/06: la clave fiscal de Erlina cambió en AFIP, pero la del sistema quedó vieja.
2. 11–15/06: el robot intentó loguear **5 días seguidos con la clave incorrecta** →
   `AUTH_FAILED` ("Clave o usuario incorrecto") cada día.
3. 16/06: AFIP detectó el patrón de intentos fallidos repetidos (señal de fuerza bruta)
   y **activó el captcha** como defensa sobre esa cuenta.
4. 16/06 → hoy: aunque la clave ya se corrigió, el captcha quedó activo; el robot no
   puede pasarlo y los reintentos diarios mantienen caliente la marca anti-bot.

**El defecto de diseño:** el auto-retry intra-día YA frena ante `auth_failed`
(`failure_classifier.is_failure_retryable` lo trata como no-retryable), pero el
**scheduler vuelve a intentar al día siguiente** indefinidamente porque
`scheduler_activo` sigue `True`. Nada pausa a un cliente con clave incorrecta ni avisa.
Eso es lo que alimenta el embudo `AUTH_FAILED → captcha`.

**Riesgo de propagación:** cualquier cliente cuya clave fiscal venza o cambie sufrirá lo
mismo. Es prevenible atacando la causa: dejar de reintentar ante clave incorrecta.

Verificado: al 23/06 ningún otro cliente tiene `auth_failed` reciente — Erlina es el
único caso, así que esta feature es prevención a futuro, no apagar un incendio masivo.

## Solución

**Auto-bloqueo inmediato:** al PRIMER `AUTH_FAILED` de una corrida del scheduler, pausar
el cliente (`scheduler_activo = False`). Cero reintentos = cero riesgo de gatillar el
captcha. El panel `/extracciones/salud` ya lo muestra en rojo accionable con el mensaje
"La clave fiscal parece incorrecta. Verificá las credenciales."

**Auto-desbloqueo preciso:** reactivar el cliente automáticamente SOLO cuando la **clave
fiscal** fue actualizada después del error — no por cualquier edición del cliente.

## Modelo de datos

Dos columnas nuevas en `taxpayer`:

- `clave_fiscal_actualizada_en: DateTime | None` — timestamp del último cambio de
  `clave_fiscal_encrypted`. Se setea al cambiar la clave (NO con otras ediciones).
  Necesario porque `updated_at` (onupdate genérico) se toca con cualquier edición y
  reactivar por editar el teléfono dispararía otro auth_failed.
- `scheduler_pausado_por_auth: Boolean NOT NULL DEFAULT False` — distingue "pausado
  automáticamente por auth_failed (auto-reactivable)" de "pausado manualmente por el
  usuario (NO auto-reactivable)".

## Bloqueo (worker)

En `_actualizar_scheduler_status` (`playwright_jobs.py`), que ya corre tras cada job de
scheduler:

- Si `final_status == "failed"` y el job tiene `failure_code == "AUTH_FAILED"`:
  - `taxpayer.scheduler_activo = False`
  - `taxpayer.scheduler_pausado_por_auth = True`
  - log `SCHEDULER_AUTO_BLOCKED | taxpayer_id=... job_id=...`
- Solo aplica a operations de scheduler (el hook ya filtra por `SCHEDULER_OPERATION_PREFIX`);
  los jobs manuales (`playwright_lpg_run`) no tocan estas columnas.
- Si el fallo es de otro tipo (timeout, network, etc.) NO se bloquea — esos son
  transitorios y se reintentan.

> Nota: el hook recibe el `job`; debe leer `job.failure_code` (ya persistido por la
> feature 077). Si `failure_code` es None (job viejo) no bloquea.

## Desbloqueo (scheduler)

En `scheduler_service.py`, al inicio del ciclo de selección de clientes a correr, ANTES
de filtrar por `scheduler_activo`:

- Buscar taxpayers con `scheduler_pausado_por_auth == True`.
- Para cada uno, si `clave_fiscal_actualizada_en` no es None y
  `clave_fiscal_actualizada_en > scheduler_ultimo_error_en` → reactivar:
  - `scheduler_activo = True`
  - `scheduler_pausado_por_auth = False`
  - log `SCHEDULER_AUTO_REACTIVATED | taxpayer_id=...`
- Un cliente con `scheduler_activo=False` y `scheduler_pausado_por_auth=False` (pausa
  manual) NUNCA se reactiva solo.

## Cambios en endpoints de clientes

En `clients.py`, donde se cambia `clave_fiscal_encrypted` (dos lugares: el endpoint de
subir clave y el PATCH de cliente cuando el payload trae `clave_fiscal`):

- Setear `item.clave_fiscal_actualizada_en = now_cordoba_naive()` junto al cambio de la
  clave, antes del commit.

## Caso Erlina (estado actual)

Erlina ya pasó de `AUTH_FAILED` a captcha, así que el auto-bloqueo no la recupera por sí
solo: el captcha quedó activo en AFIP. Para Erlina puntualmente:
- La clave ya fue corregida por el usuario.
- Hay que **enfriar la cuenta**: pausarla y dejar pasar varios días sin actividad
  automatizada para que AFIP levante el captcha.
- El auto-bloqueo de esta feature es la PREVENCIÓN para que ningún otro cliente repita el
  camino de Erlina.

## Testing

- `clave_fiscal_actualizada_en` se setea al cambiar la clave (subir-clave + PATCH con
  `clave_fiscal`), y NO al editar otros campos (PATCH sin `clave_fiscal`).
- Bloqueo: job de scheduler `failed` con `failure_code=AUTH_FAILED` →
  `scheduler_activo=False`, `scheduler_pausado_por_auth=True`.
- No bloqueo: job de scheduler `failed` con otro `failure_code` (timeout) → sin cambios.
- No bloqueo en manual: job `playwright_lpg_run` con auth_failed → no toca columnas scheduler.
- Desbloqueo: taxpayer `scheduler_pausado_por_auth=True` con
  `clave_fiscal_actualizada_en > scheduler_ultimo_error_en` → reactivado.
- No desbloqueo sin cambio de clave: `clave_fiscal_actualizada_en` None o ≤ error → sigue pausado.
- No reactivar pausa manual: `scheduler_activo=False`, `scheduler_pausado_por_auth=False`
  → nunca se reactiva.

## Archivos afectados (estimado)

- `backend/app/models/taxpayer.py` — `clave_fiscal_actualizada_en`, `scheduler_pausado_por_auth`
- `backend/migrations/versions/*` — migración (2 columnas)
- `backend/app/api/clients.py` — setear `clave_fiscal_actualizada_en` al cambiar clave (2 lugares)
- `backend/app/workers/playwright_jobs.py` — bloqueo en `_actualizar_scheduler_status`
- `backend/app/services/scheduler_service.py` — reactivación en la selección de clientes
- `backend/tests/unit/` — tests de bloqueo, desbloqueo y seteo de timestamp

## Fuera de alcance (features futuras)

- Hacer visible el screenshot del fallo (captcha) en la UI — feature siguiente.
- Resolver el captcha automáticamente — descartado (frágil, contra términos de AFIP,
  agrava la marca anti-bot).
- Enfriamiento manual de Erlina — acción operativa, no código.
