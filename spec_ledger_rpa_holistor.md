# SPEC — Ledger local de COEs + cliente API (rpa-holistor)

**Proyecto:** rpa-holistor
**Feature:** Tracking local de COEs cargados + reporte al API de liquidador-granos
**Estado:** spec aprobado, pendiente implementación
**Depende de:** [docs/integracion_ledger_coes.md](integracion_ledger_coes.md) (diseño global)
**Cross-ref:** [docs/spec_api_liquidador_granos.md](spec_api_liquidador_granos.md) (contraparte)

---

## 1. Objetivo

Evitar que rpa-holistor cargue dos veces el mismo COE en Holistor, y reportar
al liquidador-granos los COEs efectivamente cargados (para que los filtre de
futuros JSONs).

## 2. Scope

**Dentro:**
- Módulo `core/ledger.py` — wrapper SQLite con funciones puras (check, marcar, sync pendientes).
- Módulo `core/api_client.py` — cliente HTTP para la API de liquidador-granos con reintento + backoff.
- Integración en `automation/phase_executors.py`: F2 (check), F14 (marcar ok), cualquier FAIL (marcar error).
- Parser: validar `coe` obligatorio en JSON v7.1, rechazar v7 sin migrar.
- Config: `.env` con `LIQUIDADOR_API_URL`, `LIQUIDADOR_API_KEY` (gitignored).
- `tools/generar_json_prueba.py`: emitir v7.1 con `coe` sintético determinístico.
- Actualización de CLAUDE.md (sección "Contrato de entrada") y [docs/contrato_json_v7.md](contrato_json_v7.md).

**Fuera:**
- El API FastAPI en sí (vive en liquidador-granos — ver su SPEC).
- Reporting / dashboards sobre el ledger (solo queries ad-hoc vía sqlite3 por ahora).
- Migración de DBFs de Holistor para inferir COEs previamente cargados (no se hace).

## 3. Estado actual (precondiciones)

- JSON de entrada es v7 (sin campo `coe`). Ejemplo en CLAUDE.md.
- Fases registradas en [main.pyw:487-501](../main.pyw:487): F2, F3, F4, F5, F6, F7, F9, F10, F11, F12, F13, F14.
- F2 en [automation/phase_executors.py:197](../automation/phase_executors.py:197) parsea JSON/Excel → produce `liquidaciones` en `accumulated_data`.
- F14 en [automation/phase_executors.py:3883](../automation/phase_executors.py:3883) guarda el comprobante en Holistor — es el marcador real de "cargado".
- No existe `core/` — crear como paquete nuevo.
- No existe `state/` — crear, agregar al `.gitignore`.

## 4. Entregables (archivos a crear / modificar)

### Nuevos

| Path | Descripción |
|---|---|
| `core/__init__.py` | Paquete |
| `core/ledger.py` | API SQLite (sección 5) |
| `core/api_client.py` | Cliente HTTP (sección 6) |
| `core/sync_worker.py` | Drenaje de pendientes (sección 7) |
| `state/.gitkeep` | Placeholder — el `.db` se genera en runtime |
| `tests/test_ledger.py` | Tests unitarios del ledger |
| `.env.example` | Template con variables (sin secretos reales) |

### Modificados

| Path | Cambio |
|---|---|
| `parser/json_parser.py` | Soportar v7.1, validar `coe` obligatorio, calcular `hash_payload` |
| `automation/phase_executors.py` | F2: check pre-carga. F14: marcar_ok. Cualquier PhaseResult FAILED: marcar_error |
| `automation/phase_runner.py` | Propagar `ejecucion_id` UUID al iniciar batch |
| `tools/generar_json_prueba.py` | Emitir v7.1 con `coe` sintético (ej. `"99" + 12 dígitos del CUIT+nro`) |
| `.gitignore` | Agregar `state/`, `.env` |
| `CLAUDE.md` | Sección "Contrato de entrada" actualizada a v7.1, nueva sección "Ledger y sincronización" |
| `docs/contrato_json_v7.md` | Renombrar/ampliar a v7.1 (o crear `contrato_json_v7_1.md` y deprecar el viejo) |
| `requirements.txt` | Agregar `httpx` (cliente async) o `requests` (sync — más simple para un RPA single-threaded) |

## 5. Módulo `core/ledger.py`

### DDL (al inicializar la DB si no existe)

```sql
CREATE TABLE coes_cargados (
    coe                TEXT PRIMARY KEY,
    cuit_empresa       TEXT NOT NULL,
    cuit_comprador     TEXT NOT NULL,
    codigo_comprobante TEXT NOT NULL,
    tipo_pto_vta       INTEGER NOT NULL,
    nro_comprobante    INTEGER NOT NULL,
    fecha_emision      TEXT NOT NULL,
    mes                INTEGER NOT NULL,
    anio               INTEGER NOT NULL,

    estado             TEXT NOT NULL,
    error_mensaje      TEXT,
    error_fase         TEXT,

    ejecucion_id       TEXT NOT NULL,
    usuario            TEXT NOT NULL,
    cargado_en         TEXT NOT NULL,
    hash_payload       TEXT NOT NULL,

    sincronizado_api   INTEGER NOT NULL DEFAULT 0,
    sincronizado_en    TEXT,
    sync_intentos      INTEGER NOT NULL DEFAULT 0,
    sync_ultimo_error  TEXT
);

CREATE INDEX idx_coes_empresa_estado ON coes_cargados(cuit_empresa, estado);
CREATE INDEX idx_coes_pendientes_sync ON coes_cargados(sincronizado_api) WHERE sincronizado_api = 0;
```

DB path: `state/coes_cargados.db` (resolver desde raíz del repo).

### Interfaz pública (funciones puras)

```python
# core/ledger.py

from typing import Optional, Literal
from dataclasses import dataclass

Estado = Literal["ok", "error", "skipped"]

@dataclass(frozen=True)
class EntradaLedger:
    coe: str
    cuit_empresa: str
    cuit_comprador: str
    codigo_comprobante: str          # F1 | F2 | NL
    tipo_pto_vta: int
    nro_comprobante: int
    fecha_emision: str               # ISO YYYY-MM-DD
    mes: int
    anio: int
    estado: Estado
    ejecucion_id: str
    usuario: str
    cargado_en: str                  # ISO 8601 con TZ
    hash_payload: str
    error_mensaje: Optional[str] = None
    error_fase: Optional[str] = None

def init_db(db_path: str = "state/coes_cargados.db") -> None:
    """Crea la DB + tabla + índices si no existen. Idempotente."""

def existe(coe: str) -> Optional[EntradaLedger]:
    """Devuelve la entrada o None si el COE no está registrado."""

def marcar_ok(entrada: EntradaLedger) -> None:
    """INSERT con estado='ok', sincronizado_api=0.
    Si el COE ya existe con estado='ok' y mismo hash → no-op con log warning.
    Si existe con hash distinto → lanza LedgerHashMismatch (requiere decisión manual)."""

def marcar_error(entrada: EntradaLedger) -> None:
    """INSERT/UPSERT con estado='error'. error_fase y error_mensaje obligatorios."""

def marcar_skipped(coe: str, razon: str, ejecucion_id: str) -> None:
    """Registra decisión explícita de no cargar."""

def pendientes_sync(limit: int = 50) -> list[EntradaLedger]:
    """SELECT WHERE sincronizado_api = 0 ORDER BY cargado_en ASC LIMIT ?"""

def marcar_sincronizado(coe: str, sincronizado_en: str) -> None:
    """UPDATE sincronizado_api=1, sincronizado_en=?"""

def registrar_fallo_sync(coe: str, error: str) -> None:
    """UPDATE sync_intentos = sync_intentos + 1, sync_ultimo_error = ?"""
```

### Excepciones

```python
class LedgerError(Exception): ...
class LedgerHashMismatch(LedgerError):
    """COE ya existe con estado='ok' pero hash_payload difiere — datos cambiaron."""
```

### Cálculo de `hash_payload`

```python
import hashlib, json
def calcular_hash(liquidacion: dict) -> str:
    # Excluir campos volátiles/metadata al hashear
    campos_hash = {k: v for k, v in liquidacion.items()
                   if k not in ("estado_origen", "id_liquidacion")}
    payload = json.dumps(campos_hash, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

## 6. Módulo `core/api_client.py`

```python
# core/api_client.py

class APIClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0):
        ...

    def health(self) -> bool:
        """GET /v1/health — True si la API responde 200 en <2s."""

    def reportar_cargado(self, entrada: EntradaLedger) -> ResultadoSync:
        """POST /v1/coes/cargado — devuelve OK, DUPLICADO, o HASH_MISMATCH, o error."""

    def consultar_estado(self, coe: str) -> Optional[dict]:
        """GET /v1/coes/{coe} — None si 404."""
```

### `ResultadoSync`

```python
@dataclass
class ResultadoSync:
    exito: bool
    codigo: Literal["ok", "duplicado", "hash_mismatch", "timeout", "error_red", "error_servidor"]
    mensaje: str
    detalle: Optional[dict] = None
```

### Política de reintento (dentro del cliente)

- Timeout por request: 5s.
- Reintentos sincrónicos: hasta 3, con backoff `1s, 3s, 10s`.
- Si los 3 fallan → devolver `ResultadoSync(exito=False, codigo="timeout"|"error_red")`.
- No bloquea el flujo del RPA: el caller decide qué hacer (casi siempre: loggear y dejar en cola local).

### Config (lectura desde `.env`)

```
LIQUIDADOR_API_URL=http://localhost:8765
LIQUIDADOR_API_KEY=xxx
LIQUIDADOR_API_ENABLED=true        # false → skip total (modo offline)
```

Uso: `python-dotenv` cargado en `config/settings.py` (ya existe).

## 7. Módulo `core/sync_worker.py`

Drenaje de pendientes. **No es un daemon** — corre puntualmente.

```python
def drenar_pendientes(client: APIClient, max_items: int = 50) -> ResumenDrenaje:
    """
    1. SELECT pendientes_sync(limit=max_items)
    2. Para cada uno: client.reportar_cargado(...)
       - éxito → ledger.marcar_sincronizado(coe, now)
       - fallo → ledger.registrar_fallo_sync(coe, error)
    3. Devolver resumen: {total, ok, fallos, detalles}
    """

@dataclass
class ResumenDrenaje:
    total: int
    ok: int
    fallos: int
    detalles: list[str]
```

**Cuándo se invoca:**
- Al arrancar `main.pyw`, si API enabled → en thread separado, no bloquea UI.
- Después de F14 exitoso, sincrónicamente (intento inmediato — si falla, queda pendiente).
- Opcional: botón manual "Sincronizar pendientes" en la UI.

## 8. Cambios al parser (`parser/json_parser.py`)

### Validaciones nuevas

```python
def _validar_v7_1(data: dict) -> None:
    if data.get("schema_version") not in ("v7.1",):
        raise ParserError(
            f"Versión de schema no soportada: {data.get('schema_version')!r}. "
            f"Esperado 'v7.1'. Regenerar JSON con liquidador-granos >= 1.2.0."
        )

    for i, liq in enumerate(data["liquidaciones"]):
        coe = liq.get("coe")
        if not coe:
            raise ParserError(f"Liquidación #{i+1}: falta campo obligatorio 'coe'.")
        if not (isinstance(coe, str) and coe.isdigit() and len(coe) == 14):
            raise ParserError(
                f"Liquidación #{i+1}: 'coe' inválido ({coe!r}). "
                f"Debe ser string de 14 dígitos numéricos."
            )
```

### Hash de cada liquidación

Después del parseo, el parser **agrega** `_hash_payload` (con prefijo `_` para indicar
que es interno, no viene del JSON) a cada dict de liquidación:

```python
for liq in liquidaciones:
    liq["_hash_payload"] = calcular_hash(liq)
```

### Deprecación de v7

v7 sin `schema_version` → rechazar con mensaje claro. No intentar "auto-upgrade"
(sería silencioso y peligroso — el COE no se puede inferir).

## 9. Puntos de integración en fases

### F2 — check pre-carga

En [automation/phase_executors.py:197](../automation/phase_executors.py:197) (`fase_2_leer_excel`), después del parseo exitoso:

```python
from core import ledger

liquidaciones_filtradas = []
skippeadas = []
for liq in liquidaciones:
    existente = ledger.existe(liq["coe"])
    if existente is None:
        liquidaciones_filtradas.append(liq)
    elif existente.estado == "ok":
        if existente.hash_payload == liq["_hash_payload"]:
            skippeadas.append((liq["coe"], "ya_cargado"))
            if log: log(f"SKIP COE {liq['coe']}: ya cargado en {existente.cargado_en}")
        else:
            # Datos cambiaron — NO procesar automáticamente, fallar explícito
            return PhaseResult(
                phase_id=2, status=PhaseStatus.FAILED,
                message=f"COE {liq['coe']} ya está cargado pero los datos del JSON "
                        f"difieren (hash mismatch). Resolver manualmente."
            )
    elif existente.estado == "error":
        # Config flag — por ahora, fallar explícito y listar
        return PhaseResult(
            phase_id=2, status=PhaseStatus.FAILED,
            message=f"COE {liq['coe']} tiene intento previo con error en fase "
                    f"{existente.error_fase}: {existente.error_mensaje}. "
                    f"Resolver manualmente antes de reintentar."
        )
    elif existente.estado == "skipped":
        skippeadas.append((liq["coe"], "skipped_manual"))

accumulated_data["liquidaciones"] = liquidaciones_filtradas
accumulated_data["liquidaciones_skippeadas"] = skippeadas
accumulated_data["total_liquidaciones"] = len(liquidaciones_filtradas)
```

Si `liquidaciones_filtradas` queda vacío → PhaseResult SUCCESS con mensaje
"Todos los COEs ya estaban cargados" y el runner no entra al loop.

### F14 — marcar_ok

En [automation/phase_executors.py:3883](../automation/phase_executors.py:3883) (`fase_14_guardar_comprobante`), al final del happy path:

```python
from core import ledger, api_client
from datetime import datetime, timezone

liq = accumulated_data["liquidaciones"][accumulated_data["idx_liq_actual"]]
entrada = ledger.EntradaLedger(
    coe=liq["coe"],
    cuit_empresa=liq["cuit_empresa"],
    cuit_comprador=liq["cuit_comprador"],
    codigo_comprobante=liq["codigo"],
    tipo_pto_vta=liq["tipo_pto_vta"],
    nro_comprobante=liq["nro"],
    fecha_emision=liq["fecha_emision"],
    mes=liq["mes"],
    anio=liq["anio"],
    estado="ok",
    ejecucion_id=accumulated_data["ejecucion_id"],
    usuario=accumulated_data["usuario"],
    cargado_en=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    hash_payload=liq["_hash_payload"],
)
ledger.marcar_ok(entrada)

# Intento inmediato de sync (no bloquear si falla)
try:
    client = api_client.from_env()
    if client.enabled:
        client.reportar_cargado(entrada)
        ledger.marcar_sincronizado(entrada.coe, datetime.now(timezone.utc).astimezone().isoformat())
except Exception as e:
    if log: log(f"Warning: sync API falló, quedó pendiente: {e}")
```

### Cualquier fase con FAILED

Un hook en `automation/phase_runner.py` que, al capturar un `PhaseResult` con
`status=PhaseStatus.FAILED` durante el loop por liquidación, llama
`ledger.marcar_error(...)` antes de abortar el batch.

### `ejecucion_id` y `usuario`

Poblar en `accumulated_data` al inicio de `run_batch`:

```python
import uuid, getpass
accumulated_data["ejecucion_id"] = f"run_{uuid.uuid4().hex[:16]}"
accumulated_data["usuario"] = getpass.getuser()
```

## 10. Criterios de aceptación

- [ ] DB se crea automáticamente al primer uso.
- [ ] `ledger.marcar_ok()` + `ledger.existe()` devuelve la entrada correcta.
- [ ] Re-ejecutar el mismo JSON: F2 skipea todo, no se toca Holistor.
- [ ] Re-ejecutar con hash cambiado: F2 falla con mensaje claro.
- [ ] FAIL en F11 mid-batch: ledger registra `estado='error'`, `error_fase='F11'`.
- [ ] Con `LIQUIDADOR_API_ENABLED=false`: el RPA corre normal, sin intentar HTTP.
- [ ] Con API caída: F14 marca `sincronizado_api=0`, el RPA termina con éxito, hay entry pendiente.
- [ ] Al reiniciar la app con API viva: el worker drena las pendientes.
- [ ] JSON v7 sin `schema_version` → parser falla con mensaje de migración.
- [ ] JSON v7.1 sin `coe` en alguna liquidación → parser falla indicando cuál.
- [ ] `tools/generar_json_prueba.py` emite v7.1 con COEs sintéticos reproducibles.

## 11. Tests

### `tests/test_ledger.py`

- `test_init_db_idempotente` — crear 2 veces no rompe.
- `test_marcar_ok_y_existe` — happy path.
- `test_marcar_ok_duplicado_mismo_hash` — no-op, no duplica.
- `test_marcar_ok_duplicado_hash_distinto` — levanta `LedgerHashMismatch`.
- `test_pendientes_sync_orden` — orden por `cargado_en` ASC.
- `test_marcar_sincronizado` — flag a 1, timestamp poblado.

### `tests/test_api_client.py`

- Mockear con `responses` / `httpretty`.
- `test_reportar_cargado_200` — happy path.
- `test_reportar_cargado_409_hash_mismatch` — código `hash_mismatch`.
- `test_reportar_cargado_timeout_reintenta_3_veces` — verificar backoff.
- `test_api_disabled_noop` — `LIQUIDADOR_API_ENABLED=false` → no hace requests.

### `tests/test_parser_v7_1.py`

- `test_v7_sin_schema_version_falla`
- `test_v7_1_sin_coe_falla`
- `test_v7_1_coe_formato_invalido_falla` (13 dígitos, con letras, etc.)
- `test_hash_payload_estable` — mismo input → mismo hash.
- `test_hash_payload_ignora_metadata` — cambiar `estado_origen` no cambia hash.

## 12. Plan de implementación (orden sugerido)

1. **Ledger standalone** (1-2h)
   - `core/ledger.py` + tests. Sin tocar fases.
2. **Extensión parser v7.1** (1h)
   - Validación + hash. Ajustar `tools/generar_json_prueba.py`.
   - Regenerar `liquidaciones_test.json` y verificar que F2 sigue andando contra MANASRL.
3. **Hooks en fases** (2-3h)
   - F2 check, F14 marcar_ok, PhaseRunner FAIL hook.
   - `ejecucion_id` + `usuario` en `accumulated_data`.
   - Probar idempotencia end-to-end con 2 ejecuciones consecutivas del mismo JSON.
4. **Cliente API stub** (1h)
   - `core/api_client.py` con `LIQUIDADOR_API_ENABLED=false` por default — no rompe nada.
5. **Sync worker + integración en F14** (1-2h)
   - `core/sync_worker.py` + llamada en arranque de main.pyw.
6. **Coordinación con liquidador-granos** — cuando su API esté lista, flipear el flag.

## 13. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| COE colisiona entre empresas (muy improbable) | PRIMARY KEY es `coe` solo — si alguna vez ocurre, mover a `(cuit_empresa, coe)` |
| DB SQLite se corrompe | Backup automático al arranque si >7 días sin backup (fuera de scope v1) |
| Hash inestable por orden de claves | `json.dumps(..., sort_keys=True)` resuelve |
| El usuario borra `state/` sin querer | Documentar en CLAUDE.md + nombre del dir sugiere no tocar |
| API cambia contrato sin avisar | Versionar endpoints (`/v1/...`) + cliente valida `schema_version` en respuestas si aplica |
| Race al escribir desde 2 instancias del RPA | SQLite soporta WAL; documentar "una sola instancia por DB" como invariante |

## 14. Fuera de v1 (para después)

- UI en main.pyw para ver ledger (listar COEs cargados, filtrar por empresa/fecha).
- Botón "Re-sincronizar todo" manual.
- Reporting: "¿cuántas liquidaciones cargué este mes?".
- Exportar ledger a CSV.
- Soft-delete de entries (marcar como `invalidado` en vez de borrar).
