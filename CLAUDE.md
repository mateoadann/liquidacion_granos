# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Monorepo for a Grain Settlement (Liquidación de Granos) management system that integrates with Argentina's AFIP/ARCA tax authority web services. Flask REST API backend + React SPA frontend, with Playwright browser automation and RQ background jobs.

## Common Commands

### Build & Run
```bash
make up-build              # Docker full stack (background)
make run                   # Flask only, port 5001
cd frontend && npm run dev # Vite dev server, port 5173
```

### Tests
```bash
make test-local                                    # All backend tests locally
make docker-test                                   # All backend tests in Docker
cd backend && pytest tests/unit/test_validators.py -q                           # Single file
cd backend && pytest tests/unit/test_validators.py::test_valid_cuit_returns_true -q  # Single test
cd backend && pytest -k "validate_config" -q       # By keyword
```

### Static Checks (no linter configured)
```bash
cd frontend && npx tsc --noEmit          # TypeScript type check
cd frontend && npm run build             # Frontend build
cd backend && python -m compileall app tests  # Python compile check
```

### Database Migrations
```bash
make db-upgrade    # Apply migrations (local)
make db-migrate    # Generate new migration (local)
# Docker auto-runs db upgrade on backend start
```

### Pre-push Checks
```bash
make hooks-install            # Install git hook
bash scripts/pre-push-checks.sh  # Run manually
```

## Architecture

### Backend (`backend/`)
- **Entry:** `run.py` (Flask app factory), `worker.py` (RQ worker)
- **App factory:** `app/__init__.py` — creates Flask app, registers blueprints
- **Config:** `app/config.py` — reads all settings from env vars / `.env`
- **Extensions:** `app/extensions.py` — shared SQLAlchemy & Migrate instances
- **API routes** (`app/api/`): Blueprint-based. Main endpoints in `clients.py` (CRUD), `playwright.py` (job management), `jobs.py` (queue status)
- **Models** (`app/models/`): `taxpayer.py` (clients with CUIT, certs, encrypted fiscal key), `extraction_job.py`, `lpg_document.py`, `audit_event.py`
- **Services** (`app/services/`): Business logic — `crypto_service.py` (Fernet encryption), `certificate_validator.py`/`certificate_storage.py` (X509 certs), `validators.py` (CUIT), `lpg_playwright_pipeline.py` (automation orchestration)
- **Integrations** (`app/integrations/`): `arca/client.py` (SOAP via arca_arg), `playwright/lpg_consulta_client.py` (browser automation)
- **Workers** (`app/workers/`): RQ job definitions for async Playwright runs

### Frontend (`frontend/src/`)
- React 18 + TypeScript strict + Vite + Tailwind CSS
- **State:** TanStack Query for server state, Zustand for client state
- **API layer:** `clients.ts` (adapters + types), `api/client.ts` (HTTP config)
- **Hooks:** `useClients.ts` (TanStack Query hooks for client CRUD)
- **Pages:** `ClientsPage.tsx` (main), with `ClientTable.tsx`, `ClientForm.tsx`, `CertificateUpload.tsx`, `RunPlaywrightModal.tsx`, `CoeExportPanel.tsx`

### Infrastructure
- **Docker services:** postgres:16, redis:7, backend (Flask :5001), worker (RQ), frontend (Vite :5173)
- **CI:** GitHub Actions — backend compile+pytest, frontend tsc+build, Gitleaks secrets scan
- **Database:** PostgreSQL 16 with Alembic migrations in `backend/migrations/versions/`

## Key Conventions

### Python (backend)
- Flask blueprint decorators: `@bp.get`, `@bp.post`, `@bp.patch`, `@bp.delete`
- Parse body: `request.get_json(silent=True) or {}`
- Return errors as `{"error": "..."}` with proper status code
- Type hints on public functions; `from __future__ import annotations` in new typed modules
- All timestamps use **America/Argentina/Cordoba** timezone (see `app/time_utils.py`)
- Logical delete with `activo = False` where applicable
- DB pattern: `db.session.add()` + `db.session.commit()`; rollback on `IntegrityError`

### TypeScript/React (frontend)
- Strict TypeScript — do not weaken types
- 2-space indent, double quotes, semicolons
- Backend payloads are `snake_case`; frontend models can be `camelCase`; adapters centralized in `clients.ts`
- TanStack Query for all server data; local state for transient form/view state
- Convert unknown errors to safe strings: `error instanceof Error ? ... : ...`

### Testing
- pytest with fixtures in `backend/tests/conftest.py` (provides `app` with SQLite in-memory, `client`, cert fixtures)
- Test layout: `backend/tests/unit/`, `backend/tests/integration/`
- Assert both HTTP status and response payload fields

### Git Workflow
- **main** → producción. Solo recibe código a través de PR desde `dev`. No se permite push directo.
- **dev** → integración. Solo recibe código a través de PR desde ramas `feature/*`. No se permite push directo.
- **feature/NNN-slug** → ramas de trabajo. El número `NNN` es correlativo respecto al último creado (verificar con `git branch -a | grep feature/ | sort -t/ -k3 -n | tail -1`). Se crean desde `dev` y se integran vía PR a `dev`, donde deben pasar todos los checks de CI.
- **Antes de empezar a trabajar**, verificar siempre que estás en la rama correcta (`feature/*` correspondiente). Si es una feature nueva, crear la rama desde `dev` actualizado. Si es una feature existente, hacer checkout a esa rama.

## Environment

Key env vars (see `.env.example`):
- `DATABASE_URL`, `REDIS_URL` — infra connections
- `CLIENT_SECRET_KEY` — Fernet key for encrypting taxpayer fiscal keys
- `CLIENT_CERTIFICATES_BASE_PATH` — cert storage path (default `/app/certificados_clientes`)
- `ARCA_ENVIRONMENT` — `homologacion` or `produccion`
- `ARCA_CERT_PATH`, `ARCA_KEY_PATH`, `ARCA_TA_PATH` — AFIP certificate paths
- `VITE_API_BASE` — frontend API base URL (set in docker-compose)
- `PLAYWRIGHT_HEADLESS`, `PLAYWRIGHT_TIMEOUT_MS`, `PLAYWRIGHT_TYPE_DELAY_MS` — automation tuning
