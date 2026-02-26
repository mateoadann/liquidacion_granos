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
- `GET|POST|PATCH /api/taxpayers`
- `GET|POST|PATCH /api/jobs`
- `GET /api/discovery/wslpg/methods`
- `GET /api/discovery/wslpg/methods/<method_name>`
- `GET /api/wslpg/mvp/dummy`
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

Ejemplo típico en Docker:

- `ARCA_CERT_PATH=/app/data/mi_certificado.crt`
- `ARCA_KEY_PATH=/app/data/mi_clave.key`
- `ARCA_TA_PATH=/app/data/ta`

> El proyecto monta `./data` del host en `/app/data` del contenedor backend (solo lectura).
> Si ves `No such file or directory`, revisá que los archivos existan en `./data` del host.
