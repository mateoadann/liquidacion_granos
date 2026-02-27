# AGENTS.md
Guidance for coding agents working in this repository.

## 1) Repository overview
- Monorepo with Flask backend + React/Vite frontend.
- Main folders:
  - `backend/`: Flask API, SQLAlchemy models, Alembic migrations, pytest tests.
  - `frontend/`: React 18, TypeScript, Vite, TanStack Query, Zustand, Tailwind.
  - `docs/`: product and technical notes.
  - `data/`, `certificados_ws/`, `certificados_clientes/`: local cert/secret storage.
- Main tooling: `Makefile`, `docker-compose.yml`.

## 2) Setup commands
### Backend (local)
```bash
make venv
source .venv/bin/activate
make install
make env
```
Alternative:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

### Frontend (local)
```bash
cd frontend
npm install
```

### Full stack (Docker)
```bash
cp .env.example .env
docker compose up --build
```

## 3) Build, lint, and test commands
Prefer Make targets when available.

### Build
- Frontend production build: `cd frontend && npm run build`
- Docker image build: `make build` or `docker compose build`

### Lint / static checks
No dedicated lint config is currently committed (no ESLint/Ruff setup).
Use these checks as baseline:
- Frontend type check: `cd frontend && npx tsc --noEmit`
- Frontend compile sanity: `cd frontend && npm run build`
- Backend syntax/import sanity: `cd backend && python -m compileall app tests`

### Tests
- Backend full suite (local): `cd backend && pytest` or `make test-local`
- Backend full suite (docker): `make test` or `make docker-test`

### Single test execution (important)
- Single file: `cd backend && pytest tests/unit/test_validators.py -q`
- Single test function: `cd backend && pytest tests/unit/test_validators.py::test_valid_cuit_returns_true -q`
- Single integration test function: `cd backend && pytest tests/integration/test_clients_api.py::test_validate_config_complete -q`
- Filter by keyword: `cd backend && pytest -k "validate_config" -q`
- Docker single test: `docker compose exec backend pytest tests/unit/test_crypto_service.py::test_encrypt_decrypt_roundtrip -q`

### Dev run
- Backend only: `make run` (Flask on port 5001)
- Frontend only: `cd frontend && npm run dev`
- Full stack: `make up-build` or `docker compose up --build -d`

## 4) Code style and conventions
Follow nearby code and keep changes scoped.

### General
- Keep API contracts stable unless task requires contract changes.
- Do not commit secrets, certs, `.env`, or local generated artifacts.
- Prefer focused helper functions for parsing/validation and normalization.

### Python conventions (backend)
- Formatting:
  - PEP8-like style, 4-space indentation.
  - Keep functions short and readable.
- Imports order:
  1) stdlib
  2) third-party
  3) local project imports
- Typing:
  - Add type hints for new public functions and non-trivial helpers.
  - Prefer explicit return types on serializers/parsers.
  - Use `from __future__ import annotations` in new typed modules.
- Naming:
  - `snake_case` for functions/variables.
  - `PascalCase` for classes.
  - `UPPER_SNAKE_CASE` for constants.
- Flask/API patterns:
  - Use blueprint decorators (`@bp.get`, `@bp.post`, `@bp.patch`, `@bp.delete`).
  - Parse body with `request.get_json(silent=True) or {}`.
  - Return JSON errors as `{"error": "..."}` with proper status code.
  - Validate early and return early.
- Database patterns:
  - `db.session.add(...)` then `db.session.commit()`.
  - Roll back on `IntegrityError` before returning.
  - Preserve logical delete behavior (`activo = False`) where used.
- Time handling: use `datetime.utcnow()` to match existing models/endpoints.

### TypeScript/React conventions (frontend)
- TypeScript is strict (`frontend/tsconfig.json`); do not weaken types.
- Formatting seen in repo: 2-space indentation, double quotes, semicolons.
- Naming:
  - `PascalCase` for components/types/interfaces.
  - `camelCase` for variables/functions.
  - hooks start with `use`.
- Imports:
  - third-party imports first, local imports after.
  - use `type` imports where relevant.
- API boundary:
  - backend payloads are often `snake_case`.
  - frontend domain models can be `camelCase`.
  - centralize adapters/parsing in API modules (see `frontend/src/clients.ts`).
- Error handling:
  - throw `Error` with useful messages in API helpers.
  - convert unknown errors to safe strings (`error instanceof Error ? ... : ...`).
  - expose error state in UI; avoid silent failures.
- Server state:
  - use TanStack Query for fetching/mutations and cache invalidation.
  - keep transient form/view state local to components.

## 5) Testing conventions
- Framework: `pytest` (backend).
- Layout: `backend/tests/unit/`, `backend/tests/integration/`.
- Naming: files `test_*.py`, functions `test_<behavior>`.
- Reuse fixtures from `backend/tests/conftest.py` (`app`, `client`, cert fixtures).
- Prefer assertions on both HTTP status and response payload fields.
- For regressions, add focused tests near affected behavior.

## 6) Cursor and Copilot rules
Checked paths:
- `.cursor/rules/`
- `.cursorrules`
- `.github/copilot-instructions.md`
Status at time of writing: no Cursor or Copilot rule files were found.
If added later, treat them as repo-specific instructions and update this file.

## 7) Agent workflow checklist
- Before coding: identify impacted backend/frontend contract.
- During coding: keep naming, payload shape, and error semantics consistent.
- Before finishing:
  - run targeted tests (at minimum, related pytest tests),
  - run `cd frontend && npx tsc --noEmit` for TS changes,
  - run `cd frontend && npm run build` when frontend behavior changed,
  - update docs when commands or behavior change.
