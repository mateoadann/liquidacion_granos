# Diseño: Mejoras de Resiliencia para Cliente Playwright ARCA

**Fecha:** 2026-03-05
**Estado:** Aprobado
**Autor:** Claude + Mateo

## Contexto

El cliente Playwright (`lpg_consulta_client.py`) extrae COEs desde el portal de ARCA/AFIP. Actualmente experimenta fallas intermitentes por:
- Errores de red/conexión
- Páginas de error de ARCA (servicio no disponible)

El proceso se ejecuta de forma manual/esporádica y siempre en modo `headless=True`.

## Objetivo

Mejorar la resiliencia del cliente Playwright para reducir fallas por errores transitorios, manteniendo bajo perfil de automatización.

## Análisis Previo

Usando Chrome DevTools MCP se identificó:
- ARCA usa F5 BIG-IP WAF (cookies `TS*`)
- `navigator.webdriver = true` está expuesto por defecto en Playwright
- No hay reCAPTCHA visible en login
- El sitio usa JSF (JavaServer Faces)

## Diseño

### 1. Ocultamiento de Automatización

**Argumentos de Chromium:**
```python
args=[
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
]
```

**Contexto del browser:**
```python
context = browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    viewport={"width": 1366, "height": 768},
    locale="es-AR",
    timezone_id="America/Argentina/Buenos_Aires",
)
```

**Init script para ocultar webdriver:**
```python
context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
""")
```

### 2. Sistema de Reintentos

**Configuración:**
- Máximo 2 intentos por operación
- Backoff: 1 segundo entre intentos
- Aborta si el segundo intento falla (independiente de si el error es igual o diferente)
- Logging diferenciado para error repetido vs error diferente

**Flujo:**
```
Intento 1 → OK → Continuar normalmente
Intento 1 → Error A → Espera 1s → Intento 2 → OK → Continuar
Intento 1 → Error A → Espera 1s → Intento 2 → Error A → ABORT (error repetido)
Intento 1 → Error A → Espera 1s → Intento 2 → Error B → ABORT (errores distintos)
```

**Errores transitorios (reintentan):**
- `PlaywrightTimeoutError`
- Errores de red (`net::ERR_*`)
- Páginas de error de ARCA

**Errores permanentes (no reintentan):**
- Credenciales inválidas
- Empresa no encontrada
- Servicio LPG no habilitado

### 3. Pausas Humanizadas

Variación aleatoria de ±30% en los delays entre acciones:

```python
def _humanized_delay(self, base_ms: int, variance_percent: float = 0.3) -> int:
    min_delay = int(base_ms * (1 - variance_percent))
    max_delay = int(base_ms * (1 + variance_percent))
    return random.randint(min_delay, max_delay)
```

Aplicado en:
- Antes de clicks críticos (login, selección de empresa, consultar)
- Entre tipeo de campos
- Después de navegaciones

### 4. Detección de Errores de ARCA

Patrones a detectar en el contenido de la página:
- "servicio no disponible"
- "error del sistema"
- "intente más tarde"
- "sesión expirada"
- "tiempo de espera agotado"

### 5. Clasificación de Errores

```python
@dataclass
class ErrorClassification:
    is_transient: bool      # ¿Se puede reintentar?
    error_type: str         # "network", "arca_unavailable", "auth_failed", "element_not_found"
    message: str
```

## Cambios en API

**Nuevos parámetros en `LpgConsultaRequest`:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `humanize_delays` | `bool` | `True` | Activar variación aleatoria en pausas |
| `retry_max_attempts` | `int` | `2` | Máximo intentos por operación |
| `retry_base_delay_ms` | `int` | `1000` | Delay base entre reintentos |

## Archivos Afectados

**Modificar:**
- `backend/app/integrations/playwright/lpg_consulta_client.py`

**Sin cambios:**
- `backend/scripts_playwright_lpg_consulta.py`
- `backend/app/services/lpg_playwright_pipeline.py`
- API endpoints

## Compatibilidad

100% retrocompatible. Los valores por defecto mantienen el comportamiento mejorado sin requerir cambios en código cliente.

## Dependencias

Ninguna nueva. Solo se usa `random` de la stdlib de Python.
