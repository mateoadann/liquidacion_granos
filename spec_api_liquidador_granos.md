# SPEC — API + estado de COEs (liquidador-granos)

**Proyecto:** liquidador-granos (repositorio externo)
**Feature:** API REST para recibir reportes de carga de rpa-holistor + tracking
            de estado de cada COE + extensión del JSON emitido a v7.1.
**Estado:** v1 implementado y estable (auditoría 2026-05-13: 19/19 OK). v2 spec'eado, pendiente implementación en liquidador-granos.
**Depende de:** [docs/integracion_ledger_coes.md](integracion_ledger_coes.md) (diseño global)
**Cross-ref:** [docs/spec_ledger_rpa_holistor.md](spec_ledger_rpa_holistor.md) (contraparte)

> Este SPEC vive en el repo `rpa-holistor` pero describe trabajo para
> `liquidador-granos`. Copiar al otro repo al arrancar la implementación.
>
> **Parte I (§1–§15): v1** — endpoint de reporting `POST /v1/coes/cargado` y consultas `GET /v1/coes/*`. Implementado, estable.
> **Parte II (§16–§25): v2** — flujo Importar/Cargar/Ejecutar + scheduler automatizado. Pendiente implementación. Invierte el sentido del tráfico: rpa-holistor importa COEs por HTTP — reemplaza el "Exportar JSON" actual de liquidador-granos. El archivo JSON intermedio desaparece.

---

## 1. Objetivo

1. Tracking de estado de cada COE (`pendiente → descargado → cargado | error`) dentro de liquidador-granos.
2. Exponer API REST para que rpa-holistor reporte COEs cargados.
3. Incluir `coe` + metadata en el JSON v7.1 que consume rpa-holistor.
4. Filtrar COEs ya `cargado` al emitir nuevos batches (no re-enviarlos).

## 2. Scope

**Dentro:**
- Tabla `coes_estado` (o equivalente) en la DB existente de liquidador-granos.
- Endpoints REST (FastAPI): health, reportar cargado, consultar estado, listar estados.
- Auth por `X-API-Key` con valor en `.env`.
- Cambio en el emisor del JSON: versión `v7.1`, agregar `schema_version`, `meta`, y por liquidación `coe`, `id_liquidacion`, `estado_origen`.
- Transición automática de estado al descargar LPG (`pendiente → descargado`) y al recibir reporte (`descargado → cargado | error`).
- Filtrado: no incluir COEs con `estado='cargado'` en JSONs futuros (a menos que se fuerce via flag).

**Fuera:**
- UI/dashboard (fuera de v1 — inspección por endpoints o DB directa).
- Lógica de reintento desde el servidor hacia rpa-holistor (el cliente reintenta, no el server).
- Webhooks a terceros.
- Auth multi-usuario / OAuth.

## 3. Precondiciones (asumidas)

- liquidador-granos consume WebService LPG de Arca y emite un JSON consumido por rpa-holistor.
- Existe persistencia (SQL o similar) donde ya se guardan datos de LPG.
- Stack Python (consistente con el resto del ecosistema).
- Puede correr un proceso adicional (uvicorn) en la misma máquina o una cercana.

Si algo no se cumple, ajustar el SPEC antes de implementar.

## 4. Entregables

### Nuevos

| Path sugerido | Descripción |
|---|---|
| `api/__init__.py` | Paquete |
| `api/app.py` | FastAPI app con los endpoints |
| `api/schemas.py` | Modelos Pydantic de request/response |
| `api/auth.py` | Middleware `X-API-Key` |
| `api/service.py` | Lógica de negocio (upsert, filtros, transiciones) |
| `db/migrations/NNN_coes_estado.sql` | Migración de la tabla (o equivalente ORM) |
| `tests/test_api_coes.py` | Tests de endpoints |
| `.env.example` | Template con variables |
| `Dockerfile` o `docker-compose.yml` | Opcional, si se despliega containerizado |

### Modificados

| Path | Cambio |
|---|---|
| Módulo emisor de JSON | Emitir `schema_version="v7.1"`, `meta`, y por liquidación `coe`, `id_liquidacion`, `estado_origen`. Transicionar COEs a `descargado` al emitir. Filtrar `cargado` al seleccionar candidatos. |
| Módulo de ingesta LPG | Al insertar un COE nuevo desde Arca, estado inicial = `pendiente`. |
| `README.md` | Sección "API de integración con rpa-holistor" |
| `.gitignore` | Agregar `.env` |
| `requirements.txt` | Agregar `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `python-dotenv` |

## 5. Modelo de datos

### Tabla `coes_estado`

```sql
CREATE TABLE coes_estado (
    coe                   TEXT PRIMARY KEY,              -- 14 dígitos
    cuit_empresa          TEXT NOT NULL,
    cuit_comprador        TEXT,
    codigo_comprobante    TEXT,                          -- F1 | F2 | NL
    tipo_pto_vta          INTEGER,
    nro_comprobante       INTEGER,
    fecha_emision         TEXT,                          -- ISO YYYY-MM-DD
    id_liquidacion        TEXT UNIQUE,                   -- UUID generado acá al descargar

    estado                TEXT NOT NULL,                 -- pendiente | descargado | cargado | error
    descargado_en         TEXT,                          -- ISO 8601
    cargado_en            TEXT,                          -- ISO 8601
    error_mensaje         TEXT,
    error_fase            TEXT,

    ultima_ejecucion_id   TEXT,                          -- del RPA — última que reportó
    ultimo_usuario        TEXT,
    hash_payload_emitido  TEXT,                          -- lo que mandamos en el JSON
    hash_payload_cargado  TEXT,                          -- lo que el RPA reporta de vuelta

    actualizado_en        TEXT NOT NULL                  -- ISO 8601, touch on every update
);

CREATE INDEX idx_coes_estado_empresa_estado ON coes_estado(cuit_empresa, estado);
CREATE INDEX idx_coes_estado_actualizado ON coes_estado(actualizado_en);
```

### Transiciones permitidas

```
pendiente   → descargado   (al emitir JSON que incluye este COE)
descargado  → cargado      (POST /coes/cargado estado=ok)
descargado  → error        (POST /coes/cargado estado=error)
error       → cargado      (POST /coes/cargado estado=ok — reintento exitoso)
error       → descargado   (manual, al re-emitir JSON)
cargado     → cargado      (no-op, idempotente)
```

Cualquier otra transición → 409 Conflict.

### Reglas de hash

- `hash_payload_emitido` se calcula al momento de incluir el COE en un JSON,
  con el mismo algoritmo que usa rpa-holistor (ver sección 8).
- `hash_payload_cargado` viene en el `POST /coes/cargado` desde el RPA.
- Si al recibir un report los hashes difieren → guardar ambos + devolver `409 payload_mismatch`.

## 6. Endpoints

### Base URL

`http://<host>:8765/v1`

Puerto sugerido: **8765** (no colisiona con servicios comunes). Configurable via `.env`.

### Auth

Todos los endpoints excepto `/health` requieren header `X-API-Key: <key>`.
Key configurada en `.env` como `LIQUIDADOR_API_KEY`. Responde `401 api_key_invalida` si no matchea.

### `GET /v1/health`

Liveness probe. Sin auth.

```jsonc
// 200
{ "status": "ok", "timestamp": "2026-04-24T10:45:12-03:00", "version": "1.2.3" }
```

### `POST /v1/coes/cargado`

El endpoint más importante. rpa-holistor lo llama al final de F14 exitoso o ante un FAIL.

**Request:**

```jsonc
{
  "coe": "12345678901234",                       // requerido, 14 dígitos
  "ejecucion_id": "run_uuid_xyz",                // requerido
  "usuario": "mateo.adan",                       // requerido
  "cargado_en": "2026-04-24T10:45:12-03:00",     // ISO 8601 con TZ, requerido
  "estado": "ok",                                // ok | error
  "hash_payload": "sha256:...",                  // requerido

  "comprobante": {                               // requerido si estado=ok
    "codigo": "F2",
    "tipo_pto_vta": 3302,
    "nro": 30384098,
    "fecha_emision": "2026-02-26"
  },

  "error_fase": null,                            // requerido si estado=error
  "error_mensaje": null
}
```

**Responses:**

```jsonc
// 200 OK (primera vez o idempotente con mismo hash)
{
  "coe": "12345678901234",
  "estado_registrado": "cargado",   // o "error"
  "duplicado": false                // true si ya estaba con el mismo hash+ejecucion_id
}

// 409 Conflict — hash distinto
{
  "error": "payload_mismatch",
  "mensaje": "El hash del payload difiere del emitido.",
  "detalle": {
    "hash_emitido": "sha256:abc...",
    "hash_recibido": "sha256:def..."
  }
}

// 409 Conflict — transición inválida
{
  "error": "transicion_invalida",
  "mensaje": "No se puede pasar de 'pendiente' a 'cargado' sin descargar primero.",
  "detalle": { "estado_actual": "pendiente" }
}

// 401 — api key inválida
{ "error": "api_key_invalida", "mensaje": "X-API-Key faltante o inválida." }

// 422 — validación Pydantic
{ "error": "validacion_fallida", "mensaje": "...", "detalle": {...} }

// 500 — error interno
{ "error": "interno", "mensaje": "...", "detalle": {...} }
```

**Idempotencia:** mismo `(coe, ejecucion_id, hash_payload, estado)` → `duplicado: true`, no vuelve a grabar. Mismo `coe` con `ejecucion_id` distinto pero mismo `estado` y `hash` → se actualiza `ultima_ejecucion_id` + `actualizado_en`, `duplicado: false`.

### `GET /v1/coes/{coe}`

Estado actual de un COE. Para debugging / verificación puntual desde rpa-holistor.

```jsonc
// 200
{
  "coe": "12345678901234",
  "cuit_empresa": "30711165378",
  "cuit_comprador": "30708729929",
  "id_liquidacion": "liq_abc123",
  "estado": "cargado",
  "descargado_en": "2026-04-23T18:00:00-03:00",
  "cargado_en": "2026-04-24T10:45:12-03:00",
  "ultima_ejecucion_id": "run_uuid_xyz",
  "ultimo_usuario": "mateo.adan",
  "comprobante": {
    "codigo": "F2",
    "tipo_pto_vta": 3302,
    "nro": 30384098,
    "fecha_emision": "2026-02-26"
  }
}

// 404
{ "error": "coe_no_encontrado", "mensaje": "COE 12345678901234 no existe en la base." }
```

### `GET /v1/coes/estados`

Listado con filtros. Para dashboard / conciliación.

Query params:
- `cuit_empresa` (opcional)
- `estado` (opcional): `pendiente` | `descargado` | `cargado` | `error`
- `desde`, `hasta` (opcionales, ISO date)
- `limit` (default 100, max 500)
- `offset` (default 0)

```jsonc
// 200
{
  "total": 234,
  "items": [ { /* como GET /v1/coes/{coe} */ }, ... ]
}
```

### `POST /v1/coes/{coe}/forzar-estado` — (opcional, admin only)

Para correcciones manuales. Body: `{ "estado": "...", "razon": "..." }`.
Requiere header adicional `X-Admin-Token`. Queda fuera de v1 si no hay necesidad.

## 7. Cambio al JSON emitido (v7 → v7.1)

### Al seleccionar COEs para un nuevo JSON

```python
# Pseudocódigo
candidatos = db.query(
    "SELECT * FROM coes_estado "
    "WHERE cuit_empresa = ? AND estado IN ('pendiente', 'descargado') "
    "AND (fecha_emision BETWEEN ? AND ?)",
    cuit_empresa, desde, hasta
)
# NO incluir 'cargado'. 'error' queda excluido por default
# (el usuario los re-emite explícitamente con un flag si corresponde).
```

### Al emitir

1. Generar `batch_id` (ej. `b_YYYYMMDD_HHMMSS`).
2. Para cada liquidación seleccionada:
   - Asignar `id_liquidacion` si no tiene.
   - Calcular `hash_payload_emitido` (ver sección 8).
   - Transicionar `pendiente → descargado`, `descargado → descargado` (no-op, pero `descargado_en` se puede actualizar).
   - Guardar `hash_payload_emitido` y `descargado_en`.
3. Escribir JSON con estructura v7.1:

```jsonc
{
  "schema_version": "v7.1",
  "meta": {
    "generado_en": "2026-04-24T10:30:00-03:00",
    "generador": "liquidador-granos@1.2.3",
    "batch_id": "b_20260424_103000"
  },
  "liquidaciones": [
    {
      "coe": "12345678901234",
      "id_liquidacion": "liq_abc123",
      "estado_origen": "descargado",

      "cuit_empresa": "30711165378",
      "mes": 2,
      "anio": 2026,
      "cuit_comprador": "30708729929",
      "cuit_proveedor": "20102139063",

      "comprobante": { /* igual que v7 */ },
      "grano": { /* igual que v7 */ },
      "retenciones": [ /* igual que v7 */ ],
      "deducciones": [ /* igual que v7 */ ]
    }
  ]
}
```

### Retrocompatibilidad

- Emisor de JSON **solo soporta v7.1**. No hay modo legacy.
- Si se necesita compatibilidad hacia atrás (ej. pipelines viejos), agregar flag CLI `--schema-version=v7` que desactive campos nuevos. No recomendado.

## 8. Cálculo de `hash_payload` (contrato compartido)

Debe ser **idéntico** al que usa rpa-holistor. Algoritmo:

```python
import hashlib, json

def calcular_hash(liquidacion: dict) -> str:
    # Excluir campos de metadata que no afectan el contenido cargable
    campos_excluidos = {"estado_origen", "id_liquidacion"}
    payload = {k: v for k, v in liquidacion.items() if k not in campos_excluidos}
    serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serializado.encode("utf-8")).hexdigest()
```

Consideraciones:
- `sort_keys=True` es crítico — garantiza estabilidad entre Python versions / plataformas.
- Excluir campos que pueden cambiar entre emisiones sin cambiar el "contenido de negocio".
- Si algún día se agrega un campo nuevo que NO debe afectar el hash, agregar a `campos_excluidos`. Ambos repos deben updatearse juntos.

## 9. Configuración (`.env`)

```
LIQUIDADOR_API_HOST=0.0.0.0
LIQUIDADOR_API_PORT=8765
LIQUIDADOR_API_KEY=<random_string_32_chars>
LIQUIDADOR_API_DEBUG=false

# DB (según lo que ya use el proyecto)
DATABASE_URL=...
```

Key suggestion: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 10. Deployment

### Opción mínima — misma máquina que rpa-holistor

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8765 --workers 1
```

Con un único worker alcanza: el tráfico esperado es `<100 reqs/hora` (un usuario
operando el RPA). SQLite-friendly.

### Opción recomendada — systemd service / Windows service

Para que arranque al bootear el servidor donde corre liquidador-granos.

### Red

- Si rpa-holistor corre en la misma VM → `LIQUIDADOR_API_URL=http://localhost:8765`.
- Si en VMs distintas → exponer puerto 8765 en red interna, `LIQUIDADOR_API_URL=http://<ip-interna>:8765`.
- Nunca exponer a internet público — no hay auth robusta, solo API key.

### Logging

- Loggear todo request con `coe`, `ejecucion_id`, `estado`, código de respuesta.
- Archivo rotativo por día.
- Errores 5xx → nivel ERROR, con traceback.

## 11. Criterios de aceptación

- [ ] Al descargar un COE nuevo de Arca → estado `pendiente`.
- [ ] Al emitir JSON v7.1 → COEs pasan a `descargado`, se persiste `hash_payload_emitido`.
- [ ] JSON v7.1 emitido valida contra el schema definido en sección 7.
- [ ] `POST /v1/coes/cargado` con `estado=ok` → COE pasa a `cargado`, devuelve 200.
- [ ] `POST /v1/coes/cargado` idempotente — mismo payload 2x → 200 + `duplicado: true` la 2da.
- [ ] Hash mismatch → 409 con detalle.
- [ ] Transición inválida (ej. `cargado → pendiente` sin flag admin) → 409.
- [ ] Sin header `X-API-Key` → 401.
- [ ] `GET /v1/coes/{coe}` para COE inexistente → 404.
- [ ] Al generar el próximo JSON, los COEs `cargado` NO aparecen.
- [ ] `GET /v1/health` responde sin auth.
- [ ] Logs capturan request + response + latencia.

## 12. Tests

### `tests/test_api_coes.py`

- `test_health_sin_auth`
- `test_endpoints_sin_api_key_devuelven_401`
- `test_post_cargado_ok_descargado_a_cargado`
- `test_post_cargado_idempotente`
- `test_post_cargado_hash_mismatch_409`
- `test_post_cargado_desde_estado_invalido_409`
- `test_post_cargado_error_guarda_fase_y_mensaje`
- `test_get_coe_existente`
- `test_get_coe_inexistente_404`
- `test_listado_filtros_y_paginacion`

### `tests/test_emisor_json.py`

- `test_json_incluye_schema_version_v7_1`
- `test_json_incluye_meta_con_batch_id`
- `test_cada_liquidacion_tiene_coe`
- `test_coes_cargados_no_se_incluyen`
- `test_hash_emitido_es_estable`
- `test_transicion_pendiente_a_descargado_al_emitir`

### `tests/test_hash_shared.py`

**Crítico:** test que valide que el hash producido acá es idéntico al de rpa-holistor.
Mantener un fixture JSON compartido (`tests/fixtures/hash_contract.json`) con
`{"input": {...}, "hash_esperado": "sha256:..."}`. Ambos repos deben pasar el
mismo test con el mismo fixture.

## 13. Plan de implementación (orden sugerido)

1. **Migración DB** (1h) — crear tabla `coes_estado`, poblar desde datos existentes si los hay (estado inicial `descargado` si ya se emitió, si no `pendiente`).
2. **Cambio al emisor JSON** (2h) — schema v7.1, transición `pendiente → descargado`, filtro de `cargado`. Coordinar con rpa-holistor para testear con un JSON real.
3. **FastAPI skeleton + auth + health** (1h) — proyecto corre, endpoint base funciona.
4. **POST /v1/coes/cargado** (2h) — lógica de transición, idempotencia, hash check.
5. **GET /v1/coes/{coe} + listado** (1h).
6. **Tests** (2h).
7. **Deployment + logging** (1h).
8. **Integración end-to-end con rpa-holistor** (1-2h) — flipear el flag `LIQUIDADOR_API_ENABLED=true` en el otro lado y probar flujo completo.

## 14. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Hash no matchea por diferencias de serialización | Test fixture compartido entre repos (sección 12) |
| Se emite un COE pero nunca llega reporte → queda en `descargado` para siempre | Job/endpoint de "reconciliación" — fuera de v1, pero previsto |
| rpa-holistor reporta con `ejecucion_id` nuevo pero datos iguales | Idempotencia basada en `(coe, hash)`, no en `ejecucion_id` |
| API key se filtra | Rotación documentada + scope limitado a red interna |
| Transiciones concurrentes sobre el mismo COE | Lock optimista con `UPDATE ... WHERE estado = <esperado>` + retry |
| Crece mucho la tabla | Particionado por año o archivado después de N meses — fuera de v1 |

## 15. Fuera de v1 y v2

- Dashboard web con gráficos (UI del scheduler v2 queda fuera del scope de este SPEC; vive en liquidador-granos).
- Auth multi-usuario con roles.
- Export masivo del estado en CSV/Parquet.
- Métricas Prometheus.
- API key con scope por empresa (deuda; v2 asume una sola instalación de rpa-holistor).
- F15 "anular asiento en Holistor" automático. Hoy se resuelve con flag manual `requiere_revision_manual` en el ledger de rpa-holistor.
- **(Postergado a v3)** Feed incremental con cursor + tabla de eventos. Solo justifica la complejidad si el GET bulk de v2 se vuelve pesado.
- **(Postergado a v3)** Detector de anulación de COEs en Arca + estado `anulado_arca` server-side. Tolerancia de N scrapes consecutivos sin verlo. Mientras tanto la anulación se maneja manualmente.
- **(Postergado a v3)** `GET /v2/coes/{coe}` extendido con historial de transiciones. v1 cubre el caso básico de consulta puntual.

---

# Parte II — Extensión v2 (Importar/Cargar/Ejecutar + scheduler automatizado)

> v2 reemplaza el flujo "Exportar JSON" actual por un modelo **pull HTTP desde rpa-holistor**. El archivo JSON intermedio desaparece. La UI "Exportar" de liquidador-granos se quita (la herramienta de trabajo diario pasa a ser rpa-holistor).
>
> v1 (`/v1/*`) sigue vigente sin cambios — el reporting de carga del RPA al server es el mismo.

## 16. Objetivo de v2 y flujo end-to-end

### Modelo viejo ("Exportar JSON")

1. Operador entra a liquidador-granos UI.
2. Click "Exportar" → elige empresa + período.
3. Liquidador-granos genera archivo JSON v7.1 en disco.
4. Operador lleva el archivo a rpa-holistor.
5. Rpa-holistor parsea, arranca fases.

### Modelo nuevo ("Importar / Cargar / Ejecutar")

**Lado liquidador-granos:**
- Scheduler automatizado scrape-ea Arca por empresa según cadencia configurable (sin intervención).
- Quedan persistidos los COEs en `coes_estado` con `estado='descargado'`.
- La UI "Exportar" **se retira**.

**Lado rpa-holistor:**
1. **Importar** (botón sin parámetros, también dispara automáticamente al arrancar la app):
   - `GET /v2/liquidaciones?desde_fecha_emision=...` al server.
   - El cliente decide la ventana — típicamente `MAX(fecha_emision) FROM coes_cargados - 7d` como buffer, o `hoy - 90d` si el ledger está vacío.
   - Por cada liquidación en la respuesta:
     - Si **no existe** en ledger local → INSERT `estado='pendiente'`.
     - Si existe como `pendiente` → UPSERT (refresca payload).
     - Si existe como `ok`/`error`/`skipped` → ignora silenciosamente.
   - Toast: "X nuevos · Y actualizados · Z ignorados".
2. **Cargar** (botón con selector):
   - Modal: selector de período (mes + año) + selector múltiple de empresas.
   - Al confirmar, rpa-holistor filtra su ledger local por `estado='pendiente' AND cuit_empresa IN (...) AND fecha_emision BETWEEN ...`.
3. **Ejecutar**:
   - Las fases F2→F14 corren sobre la lista filtrada.
   - Cada COE termina como `ok` o `error` en el ledger.
   - F14 OK dispara `POST /v1/coes/cargado` (sin cambios).

### Por qué este modelo y no el feed con cursor

- **Paridad funcional con el "Exportar" actual** — para el operador es el mismo modelo mental (pedir un batch, decidir qué cargar), solo del otro lado del cable.
- **Idempotencia trivial**: el cliente UPSERT-ea por `coe`. Pedir lo mismo dos veces es no-op.
- **Mucho menos código server-side**: no hay `coes_eventos`, no hay cursor, no hay paginación con cursor, no hay detector de anulación.
- Para 450 liq/mes y ventanas de 6 meses (~2.700 COEs ≈ 5-15 MB), el GET bulk es perfectamente viable.
- Si en el futuro el volumen crece o necesitamos detectar cambios finos, v3 agrega cursor/eventos encima sin romper v2.

## 17. Cambios al modelo de datos

### Tabla nueva `empresas_scheduler` — config por empresa

```sql
CREATE TABLE empresas_scheduler (
    cuit_empresa        TEXT PRIMARY KEY,
    razon_social        TEXT,
    activo              INTEGER NOT NULL DEFAULT 0,   -- 0 = pausado, 1 = corre
    dias_semana         TEXT NOT NULL DEFAULT 'lun,mar,mie,jue,vie',
    hora_local          TEXT NOT NULL DEFAULT '06:00',
    ultimo_scrape_ok    TEXT,
    ultimo_scrape_error TEXT,
    actualizado_en      TEXT NOT NULL
);
```

El operador configura cada empresa desde la UI de liquidador-granos. Si `activo=0`, el scheduler la ignora.

### Tabla `coes_estado` — sin cambios

v2 NO agrega columnas. `hash_payload_arca`, `anulado_en`, `razon_anulacion`, `ultimo_scrape_en` quedan para v3 si hace falta.

### Estados server — sin cambios

Sigue siendo `pendiente | descargado | cargado | error`. No se agrega `anulado_arca` en v2.

## 18. Endpoints `/v2/*`

Todos requieren `X-API-Key` (mismo mecanismo que v1, sin cambios).

### `GET /v2/liquidaciones` — bulk del universo de COEs

Query params:

| Param | Tipo | Default | Notas |
|---|---|---|---|
| `desde_fecha_emision` | ISO date | (none) | Filtra `coes_estado.fecha_emision >= valor`. Sin parámetro → trae todo lo que el server tenga scrapeado. |
| `hasta_fecha_emision` | ISO date | (none) | Inclusivo. Útil para backfills acotados. |
| `cuit_empresa` | string repetible | (none) | Filtro opcional. Sin parámetro → todas las empresas activas en el scheduler. |

Response 200: **mismo cuerpo que el JSON v7.1 actual** del "Exportar". Esto es deliberado: rpa-holistor reusa `parser/json_parser.py` sin modificar.

```jsonc
{
  "schema_version": "v7.1",
  "meta": {
    "generado_en": "2026-05-14T10:30:00-03:00",
    "generador": "liquidador-granos@1.3.0",
    "batch_id": "b_20260514_103000",
    "fuente": "api_v2_liquidaciones",
    "filtros_aplicados": {
      "desde_fecha_emision": "2026-01-01",
      "hasta_fecha_emision": null,
      "cuit_empresa": null
    },
    "total_liquidaciones": 87
  },
  "liquidaciones": [
    {
      "coe": "12345678901234",
      "id_liquidacion": "liq_abc123",
      "estado_origen": "descargado",
      "cuit_empresa": "30711165378",
      "mes": 2,
      "anio": 2026,
      "cuit_comprador": "30708729929",
      "cuit_proveedor": "20102139063",
      "comprobante": { /* v7.1 */ },
      "grano": { /* v7.1 */ },
      "retenciones": [ /* v7.1 */ ],
      "deducciones": [ /* v7.1 */ ]
    }
  ]
}
```

Semántica:
- **No hay filtro server-side por estado**. v2 devuelve todo lo que matchea el filtro temporal/empresa, independientemente de si está `descargado`/`cargado`/`error`. **Rpa-holistor decide** qué hacer con cada COE comparando contra su ledger local (política de idempotencia §16).
- **Side-effect server-side**: ningún COE `pendiente` o `descargado` cambia de estado por servirlo en este GET. La transición `descargado → cargado` sigue siendo responsabilidad de `POST /v1/coes/cargado` (sin cambios).
- **Volumen esperado**: ~450 liq/mes × ventana 6 meses ≈ 2.700 COEs ≈ 5-15 MB JSON. Tolerable. Si pasa de 50 MB, agregar paginación simple `?limit=N&offset=M` o evolucionar a cursor (v3).

Códigos de error:

| HTTP | error | Cuándo |
|---|---|---|
| 401 | `api_key_invalida` | Header faltante o inválido. |
| 422 | `validacion_fallida` | Params mal formados (fecha inválida, etc.). |
| 503 | `scheduler_inactivo` | Informativo: el scheduler no corrió hace > 24h. El body incluye `ultimo_scrape_global`. La respuesta igual contiene `liquidaciones` (con datos potencialmente viejos). El cliente decide si igual procesa. |

### `GET /v2/empresas` — universo + config scheduler

```jsonc
// 200
{
  "total": 414,
  "ultimo_scrape_global": "2026-05-14T06:30:00-03:00",
  "empresas": [
    {
      "cuit_empresa": "30711165378",
      "razon_social": "Manassero Hnos SRL",
      "scheduler": {
        "activo": true,
        "dias_semana": ["lun", "mar", "mie", "jue", "vie"],
        "hora_local": "06:00",
        "ultimo_scrape_ok": "2026-05-14T06:15:32-03:00",
        "ultimo_scrape_error": null
      }
    }
  ]
}
```

Rpa-holistor lo usa para:
- Poblar el selector múltiple de empresas en el modal "Cargar".
- Mostrar warning si una empresa tiene `ultimo_scrape_error != null` o `ultimo_scrape_ok` desactualizado.
- Saber qué empresas existen sin tener que enumerarlas desde el ledger local.

## 19. Scheduler — config y operación

### Modelo

- Un thread/proceso del lado liquidador-granos itera `empresas_scheduler WHERE activo=1` y dispara el scrape LPG.
- Cadencia por empresa: días de la semana + hora local (TZ del server, asumido `America/Argentina/Cordoba`).
- Cada scrape de Arca actualiza `coes_estado` con los COEs nuevos detectados (`estado='descargado'` directamente; en v2 no hay distinción entre "scrapeado pero no servido" y "scrapeado y servido").
- Si el scrape falla (timeout Arca, error de auth WS LPG, etc.): registrar en `ultimo_scrape_error` con timestamp + mensaje. El próximo tick reintenta. Sin retry inmediato (Arca es rate-limit-sensible).
- Volumen esperado: ~450 liquidaciones/mes sumando todas las empresas — el scheduler no necesita ser performante, prioridad es robustez ante fallos transitorios de Arca.

### UI del scheduler (fuera del scope de este SPEC pero relevante)

Liquidador-granos expone en su UI un panel donde el operador:
- Lista empresas + estado del scheduler (verde/rojo).
- Toggle `activo` por empresa.
- Edita `dias_semana` + `hora_local`.
- Ve `ultimo_scrape_ok` y `ultimo_scrape_error`.
- Botón "Scrapear ahora" para forzar un tick manual sin esperar al cron.

La UI vieja "Exportar JSON" se retira en la misma iteración que entra el scheduler.

## 20. Flujo cliente — lado rpa-holistor

Esta sección spec'ea el comportamiento del cliente para que el spec sea autocontenido. La implementación concreta vive en el repo `rpa-holistor`.

### Importar (sin parámetros)

Triggers:
- Botón "Importar" en la UI principal.
- Automático en thread aparte al arrancar `main.pyw` (no bloquea la UI).

Algoritmo:
1. Calcular `desde_fecha_emision`:
   - Si `coes_cargados` está vacío → `hoy - 90 días`.
   - Si tiene entradas → `MAX(fecha_emision) FROM coes_cargados - 7 días` (buffer por si Arca registra COEs retroactivos).
2. `GET /v2/liquidaciones?desde_fecha_emision=...` → respuesta JSON v7.1.
3. Por cada liquidación en `response.liquidaciones`:
   - Lookup en `coes_cargados` por `coe`.
   - **No existe** → INSERT `estado='pendiente'`, `creado_en=now()`.
   - **Existe `pendiente`** → UPSERT `payload_json` (refresca por si Arca actualizó algo), bumpear `actualizado_en`.
   - **Existe `ok`/`error`/`skipped`** → no-op silencioso. No tocar.
4. Mostrar toast: `"Importados: X nuevos · Y actualizados · Z ignorados"`.
5. Si el GET falla (timeout / 5xx / `api_key_invalida`) → log + toast de error. No retry automático (el operador re-aprieta el botón si quiere).

### Cargar (con selector)

Triggers:
- Botón "Cargar" en la UI principal.

Algoritmo:
1. Modal con dos controles:
   - Selector de período: mes (1-12) + año.
   - Selector múltiple de empresas (checkboxes), poblado desde `GET /v2/empresas` cacheado al arrancar.
2. Al confirmar, ejecutar query local:
   ```sql
   SELECT * FROM coes_cargados
   WHERE estado = 'pendiente'
     AND cuit_empresa IN (...)
     AND fecha_emision BETWEEN ? AND ?
   ORDER BY fecha_emision, cuit_empresa, coe
   ```
3. Mostrar resumen previo al "Ejecutar": "Se cargarán N COEs (X de empresa A, Y de empresa B, ...)".

### Ejecutar

- Pasa la lista a `accumulated_data["liquidaciones"]`.
- Las fases F2→F14 corren igual que hoy (sin cambios).
- F14 OK → POST `/v1/coes/cargado` (sin cambios respecto a v1).

## 21. Lo que NO se implementa en v2 (queda para v3)

Decisiones de scope explícitas, postergadas para no inflar v2:

| Feature | Por qué se posterga |
|---|---|
| Tabla `coes_eventos` con cursor opaco | Para 450 liq/mes el bulk GET con filtro temporal alcanza. Cursor justifica complejidad solo si el GET se vuelve pesado o necesitamos detección fina de cambios. |
| Estado `anulado_arca` server-side + detector de anulación | Anulación en Arca de un COE ya cargado es caso raro y manejable manualmente. El detector con tolerancia de 2 scrapes es código no trivial. |
| `GET /v2/coes/{coe}` extendido con historial de transiciones | `GET /v1/coes/{coe}` cubre la consulta puntual. Historial detallado vale la pena solo cuando haya un dashboard que lo aproveche. |
| Webhooks server → cliente para invalidación inmediata | No hay caso de uso urgente. El operador hace "Importar" cuando quiere refrescar. |

## 22. Criterios de aceptación v2

### Server-side (liquidador-granos)

- [ ] Tabla `empresas_scheduler` creada con migración idempotente. Backfill de empresas existentes con `activo=0`.
- [ ] Scheduler corre como servicio. Lee `empresas_scheduler WHERE activo=1` y dispara scrape LPG según `dias_semana` + `hora_local`.
- [ ] Scheduler exitoso → COEs nuevos quedan en `coes_estado` con `estado='descargado'`.
- [ ] Scheduler con error → `ultimo_scrape_error` registrado, próximo tick reintenta sin retry inmediato.
- [ ] `GET /v2/liquidaciones` sin filtros → devuelve **todas** las liquidaciones del server en formato v7.1.
- [ ] `GET /v2/liquidaciones?desde_fecha_emision=YYYY-MM-DD` → filtra correctamente.
- [ ] `GET /v2/liquidaciones?cuit_empresa=X` (repetible) → filtra correctamente.
- [ ] `GET /v2/liquidaciones` NO modifica el estado de ningún COE.
- [ ] `GET /v2/empresas` lista todas las empresas con su config scheduler.
- [ ] UI "Exportar JSON" retirada de liquidador-granos.
- [ ] Endpoints `/v1/*` siguen funcionando sin cambios (regresión).

### Cliente-side (rpa-holistor)

- [ ] Botón "Importar" dispara GET y UPSERT según política §20.
- [ ] Importar automático al arrancar `main.pyw`, en thread, no bloquea UI.
- [ ] COE existente como `ok`/`error`/`skipped` no se sobreescribe al reimportar.
- [ ] Botón "Cargar" filtra el ledger local por período + empresas y muestra resumen previo.
- [ ] Botón "Ejecutar" corre las fases sobre la lista filtrada sin cambios.

## 23. Tests v2

### Server (liquidador-granos)

`tests/test_v2_liquidaciones.py`:
- `test_get_liquidaciones_sin_filtros_devuelve_universo_completo`
- `test_get_liquidaciones_filtra_por_desde_fecha_emision`
- `test_get_liquidaciones_filtra_por_cuit_empresa_repetible`
- `test_get_liquidaciones_no_modifica_estado_de_coes`
- `test_get_liquidaciones_devuelve_schema_v7_1_valido`
- `test_get_liquidaciones_sin_apikey_devuelve_401`

`tests/test_v2_empresas.py`:
- `test_get_empresas_lista_completa`
- `test_get_empresas_incluye_scheduler_config`

`tests/test_v2_scheduler.py`:
- `test_scheduler_respeta_dias_semana`
- `test_scheduler_respeta_hora_local`
- `test_scheduler_ignora_empresas_inactivas`
- `test_scheduler_registra_error_y_no_retira_inmediato`

### Cliente (rpa-holistor) — referencia, vive en el otro repo

- `test_importar_inserta_pendientes_nuevos`
- `test_importar_refresca_pendientes_existentes`
- `test_importar_ignora_ok_error_skipped`
- `test_cargar_filtra_ledger_por_periodo_y_empresas`

## 24. Plan de implementación v2 (orden sugerido)

### Server (liquidador-granos) — ~9h

1. **Migración DB** (1h) — crear `empresas_scheduler`, backfill empresas existentes con `activo=0`.
2. **Scheduler engine** (3h) — APScheduler o cron-driven leyendo `empresas_scheduler`. Hook al ingesta LPG existente.
3. **Endpoint `GET /v2/liquidaciones`** (2h) — reusar la lógica de armado de JSON v7.1 del "Exportar" actual, exponerla como HTTP.
4. **Endpoint `GET /v2/empresas`** (1h).
5. **Retirar UI "Exportar"** (0.5h).
6. **Tests** (1.5h).

### Cliente (rpa-holistor) — ~5h

1. **Schema del ledger** (1h) — agregar `pendiente` al CHECK de `estado` + columna `payload_json TEXT` (para cachear lo que importamos).
2. **Cliente `obtener_liquidaciones()` en [core/api_client.py](core/api_client.py)** (1h).
3. **Lógica de "Importar"** (1.5h) — UPSERT con política idempotente, integrado con UI.
4. **UI "Cargar" + "Ejecutar"** (1.5h) — modal con selectores, query al ledger local.

Integración end-to-end (~2h aparte) cuando ambos lados estén.

## 25. Cosas que NO cambian con v2

- Algoritmo de `hash_payload` (§8). Mismo fixture compartido.
- Endpoints `/v1/*`. Siguen vigentes — `POST /v1/coes/cargado` sigue siendo el cierre del ciclo cuando F14 OK.
- Estructura del JSON v7.1 dentro de `liquidacion`. El sobre cambia (HTTP response en vez de archivo) pero el contenido es idéntico — `parser/json_parser.py` del lado RPA no requiere cambios.
- Auth `X-API-Key`.
- Estados server: siguen siendo `pendiente | descargado | cargado | error`.
