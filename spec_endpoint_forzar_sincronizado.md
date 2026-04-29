# SPEC — Endpoint `forzar-sincronizado` (liquidador-granos)

**Proyecto:** liquidador-granos (repositorio externo)
**Feature:** Endpoint admin para que rpa-holistor pueda informar al server
que un COE fue cargado en Holistor pero NO matchea la validación normal de
`POST /v1/coes/cargado` (típicamente por `hash_mismatch`).
**Estado:** spec propuesto, pendiente implementación
**Depende de:** [docs/spec_api_liquidador_granos.md](spec_api_liquidador_granos.md) (API base v1)
**Cross-ref:** [docs/spec_ledger_rpa_holistor.md](spec_ledger_rpa_holistor.md) (contraparte local)

> Este SPEC vive en el repo `rpa-holistor` pero describe trabajo para
> `liquidador-granos`. Copiar al otro repo al arrancar la implementación.

---

## 1. Motivación

`POST /v1/coes/cargado` rechaza el reporte cuando `hash_payload_recibido !=
hash_payload_emitido` (código `hash_mismatch`, ver
[spec API base §6](spec_api_liquidador_granos.md)). Es la decisión correcta
en el flujo normal: protege contra que se cargue un comprobante con datos
distintos a los emitidos.

Pero hay escenarios reales donde el operador necesita **acknowledgear** la
carga aunque el hash no coincida:

1. **JSON editado a mano** para una prueba puntual o un fix de campo
   (típicamente el caso de Mateo durante el desarrollo).
2. **Re-emisión que no llegó al RPA**: el liquidador re-emitió el COE con
   datos corregidos pero el operador cargó el JSON anterior (ya cargado en
   Holistor con los datos viejos).
3. **Mapeo de retención/deducción ajustado en Holistor** después de la
   emisión del JSON, divergiendo de lo que el server tiene como hash emitido.
4. **Datos sensibles ofuscados** en el JSON antes de cargarlo (ej: razón
   social de la empresa cambia entre emisión y carga).

Hoy estos casos quedan en el ledger local con `sincronizado_api=0` y
`sync_ultimo_error="hash_mismatch: …"`. El sync_worker los reintenta en
cada arranque y siguen fallando — no hay forma de cerrar el ciclo del lado
del server salvo SQL directo.

El RPA ya implementa un override puramente **local** (`marcar_sincronizado_manual`
en `core/ledger.py`) que flagea `sincronizado_api=1` con marca de auditoría
`MANUAL: <razon> (por <usuario>)`. Falta la contraparte en el server para
que `coes_estado` también refleje el estado real.

## 2. Scope

**Dentro:**
- Nuevo endpoint `POST /v1/coes/{coe}/forzar-sincronizado`.
- Auth doble: `X-API-Key` (igual que el resto) + `X-Admin-Token` (nuevo, configurable en `.env`).
- Persistir razón obligatoria + usuario + timestamp del forzado en `coes_estado`.
- Aceptar transición desde **cualquier** estado actual hacia `cargado` o `error` (la idea es overridear).
- Idempotencia: si ya está en el estado destino con la misma razón → no-op + 200.
- Logging de audit más estricto que los endpoints normales (nivel WARNING + inclusión completa del payload).

**Fuera:**
- UI de aprobación / workflow multi-paso. Es una operación admin one-shot.
- Notificación a terceros (webhooks, email).
- Rollback automático del forzado.
- Endpoint masivo (un POST por COE alcanza para el volumen esperado).

## 3. Precondiciones

- Endpoint base `POST /v1/coes/cargado` ya implementado y operativo (ver
  [spec API base §6](spec_api_liquidador_granos.md)).
- Tabla `coes_estado` existe.
- `.env` del server soporta variables adicionales sin breaking changes.

## 4. Entregables

### Nuevos

| Path sugerido | Descripción |
|---|---|
| `api/admin.py` | Router admin con el nuevo endpoint. Separado de `api/app.py` para claridad de auth. |
| `db/migrations/NNN_coes_estado_forzado.sql` | Agrega columnas de auditoría a `coes_estado`. |
| `tests/test_api_admin.py` | Tests del endpoint. |

### Modificados

| Path | Cambio |
|---|---|
| `api/app.py` | Montar el router admin con `app.include_router(admin_router, prefix="/v1")`. |
| `api/auth.py` | Agregar dependencia `verify_admin_token` (chequea `X-Admin-Token`). |
| `.env.example` | Agregar `LIQUIDADOR_API_ADMIN_TOKEN=<random_string_32_chars>`. |
| `README.md` | Documentar la operación admin (cuándo usarla, cómo invocarla). |

## 5. Modelo de datos

### Nuevas columnas en `coes_estado`

```sql
ALTER TABLE coes_estado ADD COLUMN forzado_en           TEXT;        -- ISO 8601, NULL si nunca se forzó
ALTER TABLE coes_estado ADD COLUMN forzado_por          TEXT;        -- usuario del operador
ALTER TABLE coes_estado ADD COLUMN forzado_razon        TEXT;        -- razón libre (>= 3 chars)
ALTER TABLE coes_estado ADD COLUMN forzado_estado_previo TEXT;       -- snapshot del estado anterior al forzado
ALTER TABLE coes_estado ADD COLUMN hash_payload_forzado  TEXT;       -- hash que el RPA reportó (para audit)
```

`hash_payload_emitido` y `hash_payload_cargado` se mantienen sin cambios —
el forzado los preserva como referencia histórica.

### Política de transiciones

A diferencia de `POST /v1/coes/cargado` (que valida estricto), este endpoint
acepta:

```
*           → cargado     (con razón obligatoria)
*           → error       (con razón obligatoria + error_fase + error_mensaje)
```

Es decir: cualquier estado previo (`pendiente`, `descargado`, `cargado`, `error`)
puede ser overrideado. El estado anterior se guarda en `forzado_estado_previo`.

## 6. Endpoint

### Auth

Requiere **dos** headers:
- `X-API-Key: <key>` — igual al resto de la API. Si falla → 401 `api_key_invalida`.
- `X-Admin-Token: <token>` — nuevo, separado en `.env` como `LIQUIDADOR_API_ADMIN_TOKEN`.
  Si falla → 403 `admin_token_invalido`.

La razón de tener token separado: rotar el admin token sin invalidar la API
key normal del RPA. Y mantener el blast-radius chico — un compromiso del
key normal no permite forzar estados.

### `POST /v1/coes/{coe}/forzar-sincronizado`

**Request:**

```jsonc
{
  "estado": "cargado",                           // requerido: "cargado" | "error"
  "razon": "JSON editado a mano para test",      // requerido, >= 3 chars
  "usuario": "mateo.adan",                       // requerido
  "forzado_en": "2026-04-30T09:00:00-03:00",     // requerido, ISO 8601 con TZ
  "hash_payload_local": "sha256:...",            // requerido — el hash que tiene el RPA
                                                 //   en su ledger local. Se persiste
                                                 //   en hash_payload_forzado para audit.

  // Solo si estado="cargado":
  "comprobante": {
    "codigo": "F1",
    "tipo_pto_vta": 3301,
    "nro": 1872,
    "fecha_emision": "2025-11-07"
  },
  "ejecucion_id": "run_4214e7ca5f7f474b",        // requerido si "cargado"
  "cargado_en": "2026-04-29T14:11:49-03:00",     // requerido si "cargado"

  // Solo si estado="error":
  "error_fase": "F11",                           // requerido si "error"
  "error_mensaje": "Crash de Holistor"           // requerido si "error"
}
```

**Responses:**

```jsonc
// 200 OK — primera vez o idempotente con misma razón
{
  "coe": "330129845388",
  "estado_anterior": "descargado",          // o el que tenía
  "estado_nuevo": "cargado",                // estado tras el forzado
  "forzado_en": "2026-04-30T09:00:00-03:00",
  "duplicado": false                        // true si era no-op (ya estaba forzado igual)
}

// 200 OK — ya estaba forzado al mismo estado por el mismo motivo
{ "coe": "...", "estado_anterior": "cargado", "estado_nuevo": "cargado",
  "forzado_en": "<el original>", "duplicado": true }

// 400 — body invalido (faltan campos según estado)
{ "error": "validacion_fallida", "mensaje": "...", "detalle": {...} }

// 401 — X-API-Key faltante o inválida
{ "error": "api_key_invalida", "mensaje": "..." }

// 403 — X-Admin-Token faltante o inválido
{ "error": "admin_token_invalido", "mensaje": "..." }

// 404 — el COE no existe en coes_estado
//   (no se permite crear uno nuevo via este endpoint — el COE
//    debe haber pasado al menos por 'pendiente' a través del flujo
//    normal de descarga LPG).
{ "error": "coe_no_encontrado", "mensaje": "COE 330129845388 no existe en la base. Forzar requiere que el COE haya sido descargado previamente." }

// 422 — validación Pydantic
{ "error": "validacion_fallida", "mensaje": "...", "detalle": {...} }

// 500 — error interno
{ "error": "interno", "mensaje": "...", "detalle": {...} }
```

### Idempotencia

`(coe, estado, razon)` igual al último forzado registrado → `duplicado: true`,
no escribe. Sirve para que el RPA pueda reintentar sin pánico si la red
falla justo después del UPDATE en el server.

### Side effects

- `coes_estado.estado` ← `estado` del request.
- `coes_estado.cargado_en` ← `cargado_en` del request (si `estado="cargado"`).
- `coes_estado.error_fase` / `error_mensaje` ← del request (si `estado="error"`).
- `coes_estado.forzado_en` ← `forzado_en` del request.
- `coes_estado.forzado_por` ← `usuario`.
- `coes_estado.forzado_razon` ← `razon`.
- `coes_estado.forzado_estado_previo` ← estado actual ANTES del UPDATE.
- `coes_estado.hash_payload_forzado` ← `hash_payload_local`.
- `coes_estado.hash_payload_cargado` ← `hash_payload_local` (también se llena, para reflejar lo que el RPA tiene).
- `coes_estado.actualizado_en` ← `now()`.

`hash_payload_emitido` **no se toca** — es la fuente de verdad histórica
de lo que el server emitió originalmente.

### Logging

Cada hit de este endpoint loggea a nivel **WARNING** (más alto que los
endpoints normales en INFO):

```
WARNING [admin/forzar-sincronizado] coe=330129845388 user=mateo.adan
        estado_previo=descargado estado_nuevo=cargado
        razon='JSON editado a mano para test'
        hash_emitido=sha256:abc... hash_local=sha256:def...
```

Adicional: append-only a `logs/admin_actions.log` (path configurable).
Esto permite reconstruir todas las operaciones admin para auditoría.

## 7. Cliente del lado del RPA

### Cambios en `core/api_client.py`

Agregar método análogo a `reportar_cargado`:

```python
def forzar_sincronizado(
    self,
    coe: str,
    razon: str,
    usuario: str,
    entrada: EntradaLedger,
    admin_token: str,
) -> ResultadoSync:
    """POST /v1/coes/{coe}/forzar-sincronizado.

    A diferencia de reportar_cargado, requiere admin_token. Se pasa
    explícito (no se lee de env) para que la UI lo pida o el operador
    lo configure aparte.
    """
```

Códigos de respuesta esperados (mapear a `ResultadoSync.codigo`):
- `200` con `duplicado=False` → `"ok"`
- `200` con `duplicado=True` → `"duplicado"`
- `403 admin_token_invalido` → `"admin_token_invalido"` (nuevo código, no existía)
- `404 coe_no_encontrado` → `"not_found"`
- timeout / conexión → mismos que hoy

### Cambios en `ui/ledger_viewer.py`

Hoy `_marcar_manual` solo escribe local. Agregar:

1. Después del UPDATE local exitoso, ofrecer en el messagebox final:
   "¿Querés también forzar el estado en el server del liquidador?"
2. Si Sí → pedir `X-Admin-Token` (entry con masking). Cachear en memoria
   por la duración de la ventana — no persistir en disco.
3. Llamar `client.forzar_sincronizado(...)` con la misma razón.
4. Mostrar resultado: OK / fallo de auth / fallo de red.

Si el operador prefiere quedarse solo con el override local (server queda
desactualizado), ese flujo sigue siendo válido — no se hace mandatorio
notificar al server.

### Cambios en `core/sync_worker.py`

Sin cambios. El sync_worker no toca este endpoint — es decisión humana
explícita, no parte del drenaje automático.

## 8. Variables de entorno

### Server (liquidador-granos)

```
# Existentes
LIQUIDADOR_API_HOST=0.0.0.0
LIQUIDADOR_API_PORT=8765
LIQUIDADOR_API_KEY=<random_string_32_chars>

# Nuevo
LIQUIDADOR_API_ADMIN_TOKEN=<random_string_32_chars_distinto_al_de_arriba>
LIQUIDADOR_ADMIN_LOG_PATH=logs/admin_actions.log
```

Generar con `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

### Cliente (rpa-holistor)

No se setea en `.env` — el admin token se ingresa interactivo en la UI
cuando se va a invocar el forzado. Reduce el riesgo de filtrar el token
si el `.env` se commitea por error.

## 9. Tests

### `tests/test_api_admin.py`

- `test_forzar_sin_admin_token_devuelve_403`
- `test_forzar_con_admin_token_invalido_devuelve_403`
- `test_forzar_sin_api_key_devuelve_401`
- `test_forzar_coe_inexistente_devuelve_404`
- `test_forzar_desde_descargado_a_cargado_actualiza_estado_y_audit`
- `test_forzar_desde_cargado_a_cargado_misma_razon_es_duplicado`
- `test_forzar_desde_cargado_a_cargado_distinta_razon_actualiza_y_no_duplicado`
- `test_forzar_desde_error_a_cargado_actualiza_y_limpia_error_fields`
- `test_forzar_a_error_requiere_error_fase_y_mensaje`
- `test_forzar_persiste_hash_payload_local_en_hash_payload_forzado`
- `test_forzar_no_modifica_hash_payload_emitido`
- `test_forzar_loggea_a_admin_actions_log`

### `tests/test_admin_idempotencia.py`

- `test_dos_forzados_seguidos_iguales_segundo_es_duplicado`
- `test_forzados_concurrentes_no_corrompen_estado`

## 10. Criterios de aceptación

- [ ] Migración aplica limpia sobre DBs con datos preexistentes.
- [ ] Endpoint requiere ambos headers (API key + admin token); falta cualquiera → 401/403 según corresponda.
- [ ] `POST` con estado `cargado` actualiza estado, persiste razón/usuario/forzado_en/hash_payload_forzado.
- [ ] `POST` con estado `cargado` desde estado actual `cargado` y misma razón → 200 + `duplicado: true`.
- [ ] `POST` con estado `error` requiere `error_fase` + `error_mensaje`; sin ellos → 422.
- [ ] `forzado_estado_previo` refleja correctamente el estado pre-UPDATE.
- [ ] `hash_payload_emitido` queda intacto tras el forzado.
- [ ] Cada hit del endpoint queda logueado en `logs/admin_actions.log` con todos los campos.
- [ ] `GET /v1/coes/{coe}` devuelve los nuevos campos `forzado_*` para los COEs que pasaron por este flow.

## 11. Plan de implementación (orden sugerido)

1. **Migración DB** (1h) — `ALTER TABLE` para los 5 campos nuevos. Default NULL.
2. **`api/auth.py` — `verify_admin_token`** (30m) — dependencia FastAPI análoga a la de API key, con header distinto.
3. **`api/admin.py` — endpoint** (3h) — schemas Pydantic, lógica de transición, idempotencia, audit log.
4. **Tests** (3h) — la matriz completa de la sección 9.
5. **Actualizar `GET /v1/coes/{coe}`** (30m) — incluir los campos `forzado_*` en el response cuando estén poblados.
6. **Documentar en README** (30m) — cuándo usar este endpoint, cómo generar/rotar el admin token, ejemplos curl.
7. **Coordinar con rpa-holistor** (1h) — implementar `APIClient.forzar_sincronizado` + UI para invocarlo. Test end-to-end con el server real.

Total estimado: **~9h** del lado del server + **~2h** del lado del RPA.

## 12. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Admin token comprometido → cualquiera puede forzar estados | Token separado del API key, rotación documentada, logging completo de cada uso, scope a red interna |
| Operador forza estado por error y pierde el estado real | Snapshot en `forzado_estado_previo` + `hash_payload_emitido` intacto → reconstruir el estado pre-forzado es trivial via SQL |
| Forzados frecuentes enmascaran problemas reales del flujo | Métrica + alerta: "forzados por mes > N" → triggear review |
| Drift entre el override local del RPA y el forzado en server | El RPA persiste `MANUAL: <razon>` en `sync_ultimo_error`; el operador puede comparar contra `forzado_razon` del server. Idealmente la misma razón. |
| Concurrent writes sobre el mismo COE | Lock optimista con `UPDATE ... WHERE estado = ?` + retry. Misma estrategia que el endpoint normal. |

## 13. Fuera de v1

- Endpoint bulk para forzar varios COEs en una llamada.
- Workflow de aprobación (operador propone, admin aprueba).
- UI de "auditoría de forzados" (listado de forzados con filtros).
- Webhook a Slack/email cuando se ejecuta un forzado.
- Reversión / "deshacer forzado" con re-aplicar `forzado_estado_previo`.
- Forzado bidireccional (cargado → descargado, etc.). Si surge la necesidad,
  agregar transiciones explícitas a la lista de la sección 5.

## 14. Notas operativas

- El admin token NO se loggea (ni en server logs ni en RPA logs). Solo se
  registra que un forzado fue autenticado correctamente.
- Cuando un COE queda `forzado_en NOT NULL`, el `GET /v1/coes/{coe}` debe
  resaltarlo visualmente (ej: incluir `"forzado": true` en el response top-level)
  para que cualquier consumidor del API sepa que ese COE no pasó por el flow normal.
- La columna `forzado_en` puede usarse para queries de monitoreo:
  `SELECT COUNT(*) FROM coes_estado WHERE forzado_en > date('now', '-30 days')`.
