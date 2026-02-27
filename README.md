# Liquidación de Granos - App Base

Scaffold inicial para una herramienta de control/extracción y gestión de WSLPG (ARCA/AFIP).

## Stack

- **Frontend:** React 18, Vite, TanStack Query, Zustand, Tailwind CSS
- **Backend:** Flask 3, SQLAlchemy 2, Redis, PostgreSQL 16
- **Integración ARCA:** `arca_arg`

## Estructura

- `/frontend`: SPA React
- `/backend`: API Flask + modelos + integración ARCA
- `/docs`: documentación funcional/técnica

## Levantar con Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Servicios:

- Frontend: http://localhost:5173
- Backend: http://localhost:5001/api/health
- Postgres: localhost:5432
- Redis: localhost:6379

## Migraciones

```bash
cd backend
flask --app run.py db upgrade
```

> En Docker Compose, el servicio backend ya ejecuta `db upgrade` automáticamente al iniciar.

## Endpoints base

- `GET /api/health`
- `GET /api/clients?active=true|false`
- `POST /api/clients`
- `GET /api/clients/<id>`
- `PATCH /api/clients/<id>`
- `DELETE /api/clients/<id>` (baja logica)
- `POST /api/clients/<id>/certificates` (multipart: `cert_file`, `key_file`)
- `GET /api/clients/<id>/certificates/meta`
- `DELETE /api/clients/<id>/certificates`
- `POST /api/clients/<id>/validate-config`
- `GET /api/clients/<id>/coes/export?format=csv|xlsx&fecha_desde=DD/MM/AAAA&fecha_hasta=DD/MM/AAAA`
- `GET|POST|PATCH /api/jobs`
- `POST /api/playwright/lpg/run`
- `GET /api/playwright/lpg/jobs/<id>`
- `GET /api/discovery/wslpg/methods`
- `GET /api/discovery/wslpg/methods/<method_name>`
- `GET /api/wslpg/mvp/dummy`

## GitFlow (main + dev)

Convención de ramas:

- `main`: producción.
- `dev`: integración.
- `feature/001-descripcion-corta`: nuevas funcionalidades desde `dev`.

Flujo recomendado:

1. Crear feature desde `dev`.
2. Abrir PR de `feature/*` hacia `dev`.
3. Integrar `dev` en `main` vía PR de release/hotfix según necesidad.

Comandos base:

```bash
git checkout main
git pull
git checkout -b dev
git push -u origin dev

git checkout dev
git pull
git checkout -b feature/001-ejemplo
```

## Pre-push local (modo rápido)

Instalar hook local versionado:

```bash
make hooks-install
```

El hook ejecuta:

- `gitleaks detect` local (si está instalado)
- `python -m compileall backend/app backend/tests`
- `pytest backend/tests/unit -q`
- `npx tsc --noEmit` en frontend

Checks manuales:

```bash
bash scripts/pre-push-checks.sh
```

## GitHub Actions (full + secrets)

Se ejecutan workflows automáticos en `push` y `pull_request` hacia `main` o `dev`:

- `CI` (`.github/workflows/ci.yml`)
  - Backend full: `python -m compileall backend/app backend/tests` + `pytest backend/tests`
  - Frontend full: `npx tsc --noEmit` + `npm run build`
- `Secrets Scan` (`.github/workflows/secrets-scan.yml`)
  - Escaneo de secretos con Gitleaks
- `POST /api/wslpg/mvp/liquidacion-ultimo-nro-orden`
- `POST /api/wslpg/mvp/liquidacion-x-nro-orden`
- `POST /api/wslpg/mvp/liquidacion-x-coe`

## Discovery de `arca_arg`

```bash
cd backend
python scripts_discover_wslpg.py
```

El script intenta conectarse a `wslpg` con `arca_arg` y devuelve el listado real de métodos.

Variables recomendadas en `.env` para discovery:

- `ARCA_ENVIRONMENT=homologacion`
- `ARCA_SERVICE_NAME=wslpg`
- `ARCA_WSDL_URL` (opcional; si vacío intenta usar el default de `arca_arg.settings`)
- `ARCA_CUIT_REPRESENTADA`
- `ARCA_CERT_PATH`
- `ARCA_KEY_PATH`
- `ARCA_KEY_PASSPHRASE` (si corresponde)
- `ARCA_TA_PATH`
- `CLIENT_SECRET_KEY` (Fernet key para cifrado de clave fiscal)
- `CLIENT_CERTIFICATES_BASE_PATH` (por defecto `/app/certificados_clientes`)

Ejemplo típico en Docker:

- `ARCA_CERT_PATH=/app/data/mi_certificado.crt`
- `ARCA_KEY_PATH=/app/data/mi_clave.key`
- `ARCA_TA_PATH=/app/data/ta`

> El proyecto monta `./data` del host en `/app/data` del contenedor backend (solo lectura).
> Si ves `No such file or directory`, revisá que los archivos existan en `./data` del host.

## Playwright (MVP UI ARCA + liquidacionXCoeConsultar)

Pipeline automatizado (worker en segundo plano):

1. Login AFIP.
2. Buscar servicio con tipeo lento (delay).
3. Seleccionar empresa del cliente.
4. Ir a "Consulta Liquidaciones Recibidas".
5. Filtrar por **fecha desde** y **fecha hasta** (obligatorias).
6. Extraer COEs de la tabla.
7. Omitir COEs ya presentes en `lpg_document` para ese cliente.
8. Para COEs nuevos: ejecutar `liquidacionXCoeConsultar`.
9. Persistir resultado en `lpg_document`.
10. Pasar al siguiente cliente habilitado.

El endpoint `POST /api/playwright/lpg/run` ahora encola un job asíncrono y devuelve `202` con `job_id`.
El estado/resultados se consultan con `GET /api/playwright/lpg/jobs/<id>`.

Instalación local (backend):

```bash
cd backend
pip install -r requirements.txt
python -m playwright install chromium
```

Ejecución por `taxpayer_id` (usa CUIT/clave fiscal guardados en DB):

```bash
cd backend
python scripts_playwright_lpg_consulta.py --taxpayer-id 1 --fecha-desde 26/02/2025 --fecha-hasta 26/02/2026 --headed
```

Ejecución para **todos** los clientes activos con `playwright_enabled=true`:

```bash
cd backend
python scripts_playwright_lpg_consulta.py --fecha-desde 26/02/2025 --fecha-hasta 26/02/2026 --headed
```

Seguimiento en Docker (worker en segundo plano):

```bash
make logs SERVICE=worker
```

Si aparece el error `Executable doesn't exist ... playwright` en Docker, reconstruí backend:

```bash
docker compose build backend
docker compose up -d backend
```

Hotfix rápido (sin rebuild) sobre contenedor ya corriendo:

```bash
docker compose exec backend playwright install chromium
```

Opcional: guardar salida JSON en archivo:

```bash
python scripts_playwright_lpg_consulta.py ... --output-json /tmp/lpg_consulta.json
```
