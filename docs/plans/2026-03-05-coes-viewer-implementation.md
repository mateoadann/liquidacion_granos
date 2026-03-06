# Visualización de COEs - Plan de Implementación (Fase 4)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implementar endpoints de COEs en backend y páginas de listado/detalle de COEs en frontend con filtros y paginación.

**Architecture:** Nuevo blueprint `/api/coes` con endpoints de listado y detalle. Frontend con página de listado filtrable y paginable, más página de detalle individual.

**Tech Stack:** Flask, SQLAlchemy, React 18, React Router v6, TanStack Query, Tailwind CSS

---

## Task 1: Crear endpoint GET /api/coes (listado con filtros y paginación)

**Files:**
- Create: `backend/app/api/coes.py`
- Create: `backend/tests/integration/test_coes_api.py`
- Modify: `backend/app/api/__init__.py`

**Step 1: Crear tests**

```python
from __future__ import annotations

from app.extensions import db
from app.models import Taxpayer, LpgDocument


def _create_taxpayer(*, cuit: str, empresa: str) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.activo = True
    db.session.add(item)
    db.session.commit()
    return item


def _create_coe(*, taxpayer_id: int, coe: str, estado: str = "AC") -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.estado = estado
    doc.tipo_documento = "LPG"
    db.session.add(doc)
    db.session.commit()
    return doc


def test_list_coes_empty(client):
    response = client.get("/api/coes")
    assert response.status_code == 200
    data = response.get_json()
    assert data["coes"] == []
    assert data["total"] == 0


def test_list_coes_returns_data(client):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789012", estado="AC")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789013", estado="AN")

    response = client.get("/api/coes")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 2
    assert len(data["coes"]) == 2


def test_list_coes_filter_by_taxpayer(client):
    t1 = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    t2 = _create_taxpayer(cuit="20222222222", empresa="Otro SA")
    _create_coe(taxpayer_id=t1.id, coe="123456789012")
    _create_coe(taxpayer_id=t2.id, coe="123456789013")

    response = client.get(f"/api/coes?taxpayer_id={t1.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["coe"] == "123456789012"


def test_list_coes_filter_by_estado(client):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789012", estado="AC")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789013", estado="AN")

    response = client.get("/api/coes?estado=AC")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["estado"] == "AC"


def test_list_coes_pagination(client):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    for i in range(15):
        _create_coe(taxpayer_id=taxpayer.id, coe=f"12345678901{i:02d}")

    response = client.get("/api/coes?page=1&per_page=10")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 15
    assert len(data["coes"]) == 10
    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["pages"] == 2


def test_get_coe_detail(client):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    coe = _create_coe(taxpayer_id=taxpayer.id, coe="123456789012", estado="AC")

    response = client.get(f"/api/coes/{coe.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == coe.id
    assert data["coe"] == "123456789012"
    assert data["taxpayer"]["empresa"] == "Test SA"


def test_get_coe_not_found(client):
    response = client.get("/api/coes/99999")
    assert response.status_code == 404
```

**Step 2: Crear coes.py**

```python
from __future__ import annotations

from flask import Blueprint, request

from ..extensions import db
from ..models import LpgDocument, Taxpayer

coes_bp = Blueprint("coes", __name__, url_prefix="/api")


def _serialize_coe(doc: LpgDocument, include_taxpayer: bool = False) -> dict:
    result = {
        "id": doc.id,
        "taxpayer_id": doc.taxpayer_id,
        "coe": doc.coe,
        "pto_emision": doc.pto_emision,
        "nro_orden": doc.nro_orden,
        "estado": doc.estado,
        "tipo_documento": doc.tipo_documento,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "raw_data": doc.raw_data,
    }
    if include_taxpayer and doc.taxpayer_id:
        taxpayer = db.session.get(Taxpayer, doc.taxpayer_id)
        if taxpayer:
            result["taxpayer"] = {
                "id": taxpayer.id,
                "empresa": taxpayer.empresa,
                "cuit": taxpayer.cuit,
            }
    return result


@coes_bp.get("/coes")
def list_coes():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)  # Limitar a 100 max

    taxpayer_id = request.args.get("taxpayer_id", type=int)
    estado = request.args.get("estado", type=str)
    fecha_desde = request.args.get("fecha_desde", type=str)
    fecha_hasta = request.args.get("fecha_hasta", type=str)
    search = request.args.get("search", type=str)

    query = db.session.query(LpgDocument)

    if taxpayer_id:
        query = query.filter(LpgDocument.taxpayer_id == taxpayer_id)

    if estado:
        query = query.filter(LpgDocument.estado == estado)

    if fecha_desde:
        query = query.filter(LpgDocument.created_at >= fecha_desde)

    if fecha_hasta:
        query = query.filter(LpgDocument.created_at <= fecha_hasta)

    if search:
        query = query.filter(LpgDocument.coe.ilike(f"%{search}%"))

    total = query.count()
    pages = (total + per_page - 1) // per_page

    coes = (
        query.order_by(LpgDocument.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "coes": [_serialize_coe(c) for c in coes],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@coes_bp.get("/coes/<int:coe_id>")
def get_coe(coe_id: int):
    doc = db.session.get(LpgDocument, coe_id)
    if not doc:
        return {"error": "COE no encontrado"}, 404
    return _serialize_coe(doc, include_taxpayer=True)
```

**Step 3: Registrar blueprint**

En `backend/app/api/__init__.py`, agregar:
```python
from .coes import coes_bp
# En register_blueprints():
app.register_blueprint(coes_bp)
```

**Step 4: Ejecutar tests**

```bash
cd backend && pytest tests/integration/test_coes_api.py -v
```

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat(api): add /api/coes endpoints for listing and detail

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Crear API client y hooks para COEs en frontend

**Files:**
- Create: `frontend/src/api/coes.ts`
- Create: `frontend/src/hooks/useCoes.ts`

**Step 1: Crear coes.ts**

```tsx
import { fetchWithAuth } from "./client";

export interface Coe {
  id: number;
  taxpayer_id: number;
  coe: string;
  pto_emision: number | null;
  nro_orden: number | null;
  estado: string | null;
  tipo_documento: string;
  created_at: string | null;
  raw_data: Record<string, unknown> | null;
  taxpayer?: {
    id: number;
    empresa: string;
    cuit: string;
  };
}

export interface CoesListResponse {
  coes: Coe[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface CoesListParams {
  page?: number;
  per_page?: number;
  taxpayer_id?: number;
  estado?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  search?: string;
}

export async function listCoes(params?: CoesListParams): Promise<CoesListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", params.page.toString());
  if (params?.per_page) searchParams.set("per_page", params.per_page.toString());
  if (params?.taxpayer_id) searchParams.set("taxpayer_id", params.taxpayer_id.toString());
  if (params?.estado) searchParams.set("estado", params.estado);
  if (params?.fecha_desde) searchParams.set("fecha_desde", params.fecha_desde);
  if (params?.fecha_hasta) searchParams.set("fecha_hasta", params.fecha_hasta);
  if (params?.search) searchParams.set("search", params.search);

  const query = searchParams.toString();
  const path = query ? `/coes?${query}` : "/coes";

  const res = await fetchWithAuth(path);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener COEs");
  }
  return data;
}

export async function getCoe(id: number): Promise<Coe> {
  const res = await fetchWithAuth(`/coes/${id}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener COE");
  }
  return data;
}
```

**Step 2: Crear useCoes.ts**

```tsx
import { useQuery } from "@tanstack/react-query";
import { listCoes, getCoe, type Coe, type CoesListResponse, type CoesListParams } from "../api/coes";

export function useCoesQuery(params?: CoesListParams) {
  return useQuery<CoesListResponse, Error>({
    queryKey: ["coes", params],
    queryFn: () => listCoes(params),
    staleTime: 30000,
  });
}

export function useCoeQuery(id: number | null) {
  return useQuery<Coe, Error>({
    queryKey: ["coe", id],
    queryFn: () => getCoe(id!),
    enabled: id !== null && id > 0,
  });
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/coes.ts frontend/src/hooks/useCoes.ts
git commit -m "feat(api): add COEs API client and hooks

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Crear componente Pagination

**Files:**
- Create: `frontend/src/components/ui/Pagination.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Crear Pagination.tsx**

```tsx
import { Button } from "./Button";

interface PaginationProps {
  page: number;
  pages: number;
  total: number;
  perPage: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pages, total, perPage, onPageChange }: PaginationProps) {
  if (pages <= 1) return null;

  const start = (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, total);

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200">
      <div className="text-sm text-slate-600">
        Mostrando {start} - {end} de {total}
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Anterior
        </Button>
        <span className="text-sm text-slate-600">
          Página {page} de {pages}
        </span>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
        >
          Siguiente
        </Button>
      </div>
    </div>
  );
}
```

**Step 2: Actualizar index.ts**

Agregar:
```tsx
export { Pagination } from "./Pagination";
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(ui): add Pagination component

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Crear página CoesListPage

**Files:**
- Create: `frontend/src/pages/CoesListPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx`

**Step 1: Crear CoesListPage.tsx**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import {
  Card,
  Badge,
  Spinner,
  Alert,
  SearchInput,
  Select,
  Input,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  Pagination,
  Button,
} from "../components/ui";
import { useCoesQuery } from "../hooks/useCoes";
import { useClientsQuery } from "../useClients";

function EstadoBadge({ estado }: { estado: string | null }) {
  const variants: Record<string, "success" | "warning" | "error" | "default"> = {
    AC: "success",
    AN: "error",
    PE: "warning",
  };
  const labels: Record<string, string> = {
    AC: "Activo",
    AN: "Anulado",
    PE: "Pendiente",
  };
  return (
    <Badge variant={variants[estado ?? ""] ?? "default"}>
      {labels[estado ?? ""] ?? estado ?? "-"}
    </Badge>
  );
}

export function CoesListPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [taxpayerId, setTaxpayerId] = useState<number | undefined>();
  const [estado, setEstado] = useState<string>("");

  const clientsQuery = useClientsQuery();
  const coesQuery = useCoesQuery({
    page,
    per_page: 20,
    taxpayer_id: taxpayerId,
    estado: estado || undefined,
    search: search || undefined,
  });

  const clients = clientsQuery.data ?? [];

  function handleSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function handleTaxpayerChange(value: string) {
    setTaxpayerId(value ? Number(value) : undefined);
    setPage(1);
  }

  function handleEstadoChange(value: string) {
    setEstado(value);
    setPage(1);
  }

  return (
    <div>
      <PageHeader
        title="COEs"
        subtitle={coesQuery.data ? `${coesQuery.data.total} documentos` : undefined}
      />

      <Card padding="none">
        {/* Filtros */}
        <div className="p-4 border-b border-slate-200 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <SearchInput
              value={search}
              onChange={handleSearch}
              placeholder="Buscar por COE..."
            />
            <Select
              value={taxpayerId?.toString() ?? ""}
              onChange={(e) => handleTaxpayerChange(e.target.value)}
              options={[
                { value: "", label: "Todos los clientes" },
                ...clients.map((c) => ({ value: c.id.toString(), label: c.empresa })),
              ]}
            />
            <Select
              value={estado}
              onChange={(e) => handleEstadoChange(e.target.value)}
              options={[
                { value: "", label: "Todos los estados" },
                { value: "AC", label: "Activo" },
                { value: "AN", label: "Anulado" },
                { value: "PE", label: "Pendiente" },
              ]}
            />
          </div>
        </div>

        {/* Tabla */}
        {coesQuery.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : coesQuery.isError ? (
          <div className="p-4">
            <Alert variant="error">Error al cargar COEs</Alert>
          </div>
        ) : coesQuery.data?.coes.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            No se encontraron COEs
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableCell header>COE</TableCell>
                  <TableCell header>Cliente</TableCell>
                  <TableCell header>Fecha</TableCell>
                  <TableCell header>Estado</TableCell>
                  <TableCell header className="w-20"></TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coesQuery.data?.coes.map((coe) => {
                  const client = clients.find((c) => c.id === coe.taxpayer_id);
                  return (
                    <TableRow key={coe.id}>
                      <TableCell className="font-mono">{coe.coe ?? "-"}</TableCell>
                      <TableCell>{client?.empresa ?? `ID: ${coe.taxpayer_id}`}</TableCell>
                      <TableCell className="text-slate-600">
                        {coe.created_at
                          ? new Date(coe.created_at).toLocaleDateString("es-AR")
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <EstadoBadge estado={coe.estado} />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => navigate(`/coes/${coe.id}`)}
                        >
                          Ver
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>

            {coesQuery.data ? (
              <Pagination
                page={coesQuery.data.page}
                pages={coesQuery.data.pages}
                total={coesQuery.data.total}
                perPage={coesQuery.data.per_page}
                onPageChange={setPage}
              />
            ) : null}
          </>
        )}
      </Card>
    </div>
  );
}
```

**Step 2: Actualizar Layout.tsx**

Agregar link a COEs en la navbar:
```tsx
<NavLink to="/coes" className={linkClass}>
  COEs
</NavLink>
```

**Step 3: Actualizar App.tsx**

Agregar ruta:
```tsx
import { CoesListPage } from "./pages/CoesListPage";
// ...
<Route path="/coes" element={<CoesListPage />} />
```

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(coes): add COEs list page with filters and pagination

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Crear página CoeDetailPage

**Files:**
- Create: `frontend/src/pages/CoeDetailPage.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Crear CoeDetailPage.tsx**

```tsx
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, CardHeader, Badge, Button, Spinner, Alert } from "../components/ui";
import { useCoeQuery } from "../hooks/useCoes";

function EstadoBadge({ estado }: { estado: string | null }) {
  const variants: Record<string, "success" | "warning" | "error" | "default"> = {
    AC: "success",
    AN: "error",
    PE: "warning",
  };
  const labels: Record<string, string> = {
    AC: "Activo",
    AN: "Anulado",
    PE: "Pendiente",
  };
  return (
    <Badge variant={variants[estado ?? ""] ?? "default"}>
      {labels[estado ?? ""] ?? estado ?? "-"}
    </Badge>
  );
}

export function CoeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const coeId = Number(id);

  const coeQuery = useCoeQuery(coeId);
  const coe = coeQuery.data;

  if (coeQuery.isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (coeQuery.isError || !coe) {
    return (
      <div>
        <PageHeader title="Error" />
        <Alert variant="error">COE no encontrado</Alert>
        <Button variant="secondary" onClick={() => navigate("/coes")} className="mt-4">
          Volver a COEs
        </Button>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={`COE: ${coe.coe ?? "Sin número"}`}
        subtitle={coe.taxpayer?.empresa}
        actions={
          <Button variant="secondary" onClick={() => navigate("/coes")}>
            Volver
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Información del Documento" />
          <dl className="space-y-4">
            <div>
              <dt className="text-sm font-medium text-slate-500">COE</dt>
              <dd className="mt-1 font-mono text-slate-900">{coe.coe ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Estado</dt>
              <dd className="mt-1">
                <EstadoBadge estado={coe.estado} />
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Tipo Documento</dt>
              <dd className="mt-1 text-slate-900">{coe.tipo_documento}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Punto Emisión</dt>
              <dd className="mt-1 text-slate-900">{coe.pto_emision ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Número Orden</dt>
              <dd className="mt-1 text-slate-900">{coe.nro_orden ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Fecha Creación</dt>
              <dd className="mt-1 text-slate-900">
                {coe.created_at
                  ? new Date(coe.created_at).toLocaleString("es-AR")
                  : "-"}
              </dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHeader title="Cliente" />
          {coe.taxpayer ? (
            <dl className="space-y-4">
              <div>
                <dt className="text-sm font-medium text-slate-500">Empresa</dt>
                <dd className="mt-1 text-slate-900">{coe.taxpayer.empresa}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-slate-500">CUIT</dt>
                <dd className="mt-1 font-mono text-slate-900">{coe.taxpayer.cuit}</dd>
              </div>
              <div className="pt-4 border-t border-slate-200">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/clientes/${coe.taxpayer!.id}`)}
                >
                  Ver cliente
                </Button>
              </div>
            </dl>
          ) : (
            <p className="text-slate-500">Cliente no disponible</p>
          )}
        </Card>

        {coe.raw_data ? (
          <Card className="lg:col-span-2">
            <CardHeader title="Datos Crudos" />
            <pre className="bg-slate-50 p-4 rounded-lg text-xs overflow-x-auto">
              {JSON.stringify(coe.raw_data, null, 2)}
            </pre>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
```

**Step 2: Actualizar App.tsx**

Agregar ruta:
```tsx
import { CoeDetailPage } from "./pages/CoeDetailPage";
// ...
<Route path="/coes/:id" element={<CoeDetailPage />} />
```

**Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(coes): add COE detail page

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Tests y verificación final

**Step 1: Ejecutar tests de backend**

```bash
cd backend && pytest -v
```

**Step 2: Verificar build de frontend**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

---

## Task 7: Push y crear PR

**Step 1: Push**

```bash
git push -u origin feature/006-coes-viewer
```

**Step 2: Crear PR**

```bash
gh pr create --base dev --title "feat(ui): Visualización de COEs - Fase 4" --body "$(cat <<'EOF'
## Summary

### Backend
- Nuevo blueprint `/api/coes` con endpoints:
  - `GET /api/coes` - Listado con filtros y paginación
  - `GET /api/coes/:id` - Detalle de COE individual
- Tests de integración para endpoints

### Frontend
- API client y hooks para COEs
- Componente Pagination reutilizable
- CoesListPage con filtros (cliente, estado, búsqueda) y paginación
- CoeDetailPage con información completa
- Link a COEs en navbar

## Test plan

- [ ] Backend tests pasan (`pytest -v`)
- [ ] Frontend build exitoso (`npm run build`)
- [ ] Listado de COEs muestra datos correctamente
- [ ] Filtros funcionan (cliente, estado, búsqueda)
- [ ] Paginación funciona
- [ ] Detalle de COE muestra toda la información
- [ ] Navegación entre páginas funciona

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
