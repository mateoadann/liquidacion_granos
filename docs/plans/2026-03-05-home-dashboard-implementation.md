# Home Dashboard Implementation Plan (Fase 2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implementar página Home Dashboard con métricas del sistema, panel de ejecución Playwright mejorado, y componentes UI adicionales.

**Architecture:** Reutilizar endpoints existentes (`/clients`, `/jobs`) para estadísticas. Nuevo endpoint `/api/stats` para métricas agregadas. Mover lógica de ejecución Playwright desde ClientsPage a HomePage. Componentes Card, Badge, Select para UI.

**Tech Stack:** React 18, React Router v6, TanStack Query, Zustand, Tailwind CSS

---

## Task 1: Crear endpoint de estadísticas en backend

**Files:**
- Create: `backend/app/api/stats.py`
- Create: `backend/tests/integration/test_stats_api.py`
- Modify: `backend/app/api/__init__.py`

**Step 1: Escribir tests**

Crear `backend/tests/integration/test_stats_api.py`:

```python
from __future__ import annotations

from app.extensions import db
from app.models import Taxpayer, ExtractionJob, LpgDocument


def _create_taxpayer(*, cuit: str, empresa: str, activo: bool = True, playwright_enabled: bool = True) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.playwright_enabled = playwright_enabled
    item.activo = activo
    db.session.add(item)
    db.session.commit()
    return item


def _create_job(*, taxpayer_id: int, status: str, operation: str = "playwright_lpg_run") -> ExtractionJob:
    job = ExtractionJob()
    job.taxpayer_id = taxpayer_id
    job.operation = operation
    job.status = status
    job.payload = {}
    db.session.add(job)
    db.session.commit()
    return job


def _create_coe(*, taxpayer_id: int, coe: str) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.pto_emision = 1
    doc.nro_orden = 1
    doc.estado = "AC"
    doc.raw_data = {}
    db.session.add(doc)
    db.session.commit()
    return doc


class TestStatsEndpoint:
    def test_stats_returns_counts(self, client):
        t1 = _create_taxpayer(cuit="20111111111", empresa="Empresa 1", activo=True)
        t2 = _create_taxpayer(cuit="20222222222", empresa="Empresa 2", activo=True)
        _create_taxpayer(cuit="20333333333", empresa="Empresa 3", activo=False)

        _create_job(taxpayer_id=t1.id, status="completed")
        _create_job(taxpayer_id=t1.id, status="completed")
        _create_job(taxpayer_id=t2.id, status="failed")

        _create_coe(taxpayer_id=t1.id, coe="123456789")
        _create_coe(taxpayer_id=t1.id, coe="123456790")
        _create_coe(taxpayer_id=t2.id, coe="123456791")

        response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.get_json()
        assert data["clients_active"] == 2
        assert data["clients_inactive"] == 1
        assert data["clients_total"] == 3
        assert data["jobs_total"] == 3
        assert data["jobs_completed"] == 2
        assert data["jobs_failed"] == 1
        assert data["coes_total"] == 3

    def test_stats_empty_db(self, client):
        response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.get_json()
        assert data["clients_active"] == 0
        assert data["clients_total"] == 0
        assert data["jobs_total"] == 0
        assert data["coes_total"] == 0
```

**Step 2: Ejecutar tests y verificar que fallan**

Run: `cd backend && pytest tests/integration/test_stats_api.py -v`

**Step 3: Implementar endpoint**

Crear `backend/app/api/stats.py`:

```python
from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import func

from ..extensions import db
from ..models import Taxpayer, ExtractionJob, LpgDocument
from ..middleware import require_auth

stats_bp = Blueprint("stats", __name__)


@stats_bp.get("/stats")
@require_auth
def get_stats():
    """Retorna estadísticas agregadas del sistema."""
    # Clientes
    clients_active = db.session.query(func.count(Taxpayer.id)).filter(
        Taxpayer.activo == True
    ).scalar() or 0

    clients_inactive = db.session.query(func.count(Taxpayer.id)).filter(
        Taxpayer.activo == False
    ).scalar() or 0

    clients_total = clients_active + clients_inactive

    # Jobs
    jobs_total = db.session.query(func.count(ExtractionJob.id)).scalar() or 0

    jobs_completed = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "completed"
    ).scalar() or 0

    jobs_failed = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "failed"
    ).scalar() or 0

    jobs_pending = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "pending"
    ).scalar() or 0

    jobs_running = db.session.query(func.count(ExtractionJob.id)).filter(
        ExtractionJob.status == "running"
    ).scalar() or 0

    # Último job
    last_job = db.session.query(ExtractionJob).order_by(
        ExtractionJob.created_at.desc()
    ).first()

    # COEs
    coes_total = db.session.query(func.count(LpgDocument.id)).scalar() or 0

    return jsonify({
        "clients_active": clients_active,
        "clients_inactive": clients_inactive,
        "clients_total": clients_total,
        "jobs_total": jobs_total,
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        "jobs_pending": jobs_pending,
        "jobs_running": jobs_running,
        "coes_total": coes_total,
        "last_job": last_job.to_dict() if last_job else None,
    }), 200
```

**Step 4: Registrar blueprint**

En `backend/app/api/__init__.py`, agregar:
- Import: `from .stats import stats_bp`
- En `register_blueprints`: `app.register_blueprint(stats_bp, url_prefix="/api")`

**Step 5: Ejecutar tests**

Run: `cd backend && pytest tests/integration/test_stats_api.py -v`

**Step 6: Commit**

```bash
git add backend/app/api/stats.py backend/app/api/__init__.py backend/tests/integration/test_stats_api.py
git commit -m "feat(api): add /stats endpoint for dashboard metrics

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Crear componentes UI adicionales (Card, Badge, Select)

**Files:**
- Create: `frontend/src/components/ui/Card.tsx`
- Create: `frontend/src/components/ui/Badge.tsx`
- Create: `frontend/src/components/ui/Select.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Crear Card.tsx**

```tsx
import { type ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingClasses = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
};

export function Card({ children, className = "", padding = "md" }: CardProps) {
  return (
    <div
      className={`
        bg-white rounded-lg border border-slate-200 shadow-sm
        ${paddingClasses[padding]}
        ${className}
      `}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function CardHeader({ title, subtitle, action }: CardHeaderProps) {
  return (
    <div className="flex items-start justify-between mb-4">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        {subtitle ? (
          <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}
```

**Step 2: Crear Badge.tsx**

```tsx
type BadgeVariant = "default" | "success" | "warning" | "error" | "info";
type BadgeSize = "sm" | "md";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-slate-100 text-slate-700",
  success: "bg-emerald-100 text-emerald-700",
  warning: "bg-amber-100 text-amber-700",
  error: "bg-red-100 text-red-700",
  info: "bg-blue-100 text-blue-700",
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-2.5 py-1 text-sm",
};

export function Badge({
  children,
  variant = "default",
  size = "sm",
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center font-medium rounded-full
        ${variantClasses[variant]}
        ${sizeClasses[size]}
        ${className}
      `}
    >
      {children}
    </span>
  );
}
```

**Step 3: Crear Select.tsx**

```tsx
import { type SelectHTMLAttributes, forwardRef } from "react";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, className = "", id, ...props }, ref) => {
    const selectId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="w-full">
        {label ? (
          <label
            htmlFor={selectId}
            className="block text-sm font-medium text-slate-700 mb-1"
          >
            {label}
          </label>
        ) : null}
        <select
          ref={ref}
          id={selectId}
          className={`
            w-full px-3 py-2 rounded-md border text-sm
            focus:outline-none focus:ring-2 focus:ring-offset-0
            disabled:bg-slate-100 disabled:cursor-not-allowed
            ${
              error
                ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                : "border-slate-300 focus:ring-green-500 focus:border-green-500"
            }
            ${className}
          `}
          {...props}
        >
          {placeholder ? (
            <option value="">{placeholder}</option>
          ) : null}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error ? (
          <p className="mt-1 text-xs text-red-600">{error}</p>
        ) : null}
      </div>
    );
  }
);

Select.displayName = "Select";
```

**Step 4: Actualizar index.ts**

```tsx
export { Button } from "./Button";
export { Input } from "./Input";
export { Alert } from "./Alert";
export { Spinner } from "./Spinner";
export { Card, CardHeader } from "./Card";
export { Badge } from "./Badge";
export { Select } from "./Select";
```

**Step 5: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(ui): add Card, Badge, and Select components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Crear API client para stats y jobs

**Files:**
- Create: `frontend/src/api/stats.ts`
- Create: `frontend/src/api/jobs.ts`

**Step 1: Crear stats.ts**

```tsx
import { fetchWithAuth } from "./client";

export interface DashboardStats {
  clients_active: number;
  clients_inactive: number;
  clients_total: number;
  jobs_total: number;
  jobs_completed: number;
  jobs_failed: number;
  jobs_pending: number;
  jobs_running: number;
  coes_total: number;
  last_job: {
    id: number;
    operation: string;
    status: string;
    created_at: string;
    finished_at: string | null;
  } | null;
}

export async function getStats(): Promise<DashboardStats> {
  const res = await fetchWithAuth("/stats");
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener estadísticas");
  }
  return data;
}
```

**Step 2: Crear jobs.ts**

```tsx
import { fetchWithAuth } from "./client";

export interface Job {
  id: number;
  taxpayer_id: number | null;
  operation: string;
  status: "pending" | "running" | "completed" | "failed";
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobsListResponse {
  jobs: Job[];
  total: number;
}

export async function listJobs(params?: {
  status?: string;
  limit?: number;
}): Promise<JobsListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.limit) searchParams.set("limit", params.limit.toString());

  const query = searchParams.toString();
  const path = query ? `/jobs?${query}` : "/jobs";

  const res = await fetchWithAuth(path);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener jobs");
  }
  return data;
}

export async function getJob(id: number): Promise<Job> {
  const res = await fetchWithAuth(`/jobs/${id}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener job");
  }
  return data;
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/stats.ts frontend/src/api/jobs.ts
git commit -m "feat(api): add stats and jobs API clients

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Crear hooks para stats y jobs

**Files:**
- Create: `frontend/src/hooks/useStats.ts`
- Create: `frontend/src/hooks/useJobs.ts`

**Step 1: Crear useStats.ts**

```tsx
import { useQuery } from "@tanstack/react-query";
import { getStats, type DashboardStats } from "../api/stats";

export function useStatsQuery() {
  return useQuery<DashboardStats, Error>({
    queryKey: ["stats"],
    queryFn: getStats,
    refetchInterval: 30000, // Refrescar cada 30 segundos
    staleTime: 10000,
  });
}
```

**Step 2: Crear useJobs.ts**

```tsx
import { useQuery } from "@tanstack/react-query";
import { listJobs, getJob, type Job, type JobsListResponse } from "../api/jobs";

export function useJobsQuery(params?: { status?: string; limit?: number }) {
  return useQuery<JobsListResponse, Error>({
    queryKey: ["jobs", params],
    queryFn: () => listJobs(params),
    refetchInterval: (query) => {
      // Si hay jobs pending/running, refrescar más seguido
      const data = query.state.data;
      if (data?.jobs.some((j) => j.status === "pending" || j.status === "running")) {
        return 3000;
      }
      return 30000;
    },
    staleTime: 5000,
  });
}

export function useJobQuery(id: number | null) {
  return useQuery<Job, Error>({
    queryKey: ["job", id],
    queryFn: () => getJob(id!),
    enabled: id !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "pending" || status === "running") {
        return 3000;
      }
      return false;
    },
  });
}
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(hooks): add useStats and useJobs hooks

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Crear componente StatsCards

**Files:**
- Create: `frontend/src/components/dashboard/StatsCards.tsx`
- Create: `frontend/src/components/dashboard/index.ts`

**Step 1: Crear StatsCards.tsx**

```tsx
import { Card } from "../ui";
import { Spinner } from "../ui";
import type { DashboardStats } from "../../api/stats";

interface StatsCardsProps {
  stats: DashboardStats | undefined;
  isLoading: boolean;
}

interface StatCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  color?: "green" | "amber" | "red" | "blue" | "slate";
}

function StatCard({ title, value, subtitle, color = "slate" }: StatCardProps) {
  const colorClasses = {
    green: "text-green-600",
    amber: "text-amber-600",
    red: "text-red-600",
    blue: "text-blue-600",
    slate: "text-slate-900",
  };

  return (
    <Card>
      <p className="text-sm font-medium text-slate-500">{title}</p>
      <p className={`text-3xl font-bold mt-1 ${colorClasses[color]}`}>
        {value}
      </p>
      {subtitle ? (
        <p className="text-xs text-slate-400 mt-1">{subtitle}</p>
      ) : null}
    </Card>
  );
}

export function StatsCards({ stats, isLoading }: StatsCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="flex items-center justify-center h-24">
            <Spinner size="md" />
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        title="Clientes Activos"
        value={stats?.clients_active ?? 0}
        subtitle={`${stats?.clients_inactive ?? 0} inactivos`}
        color="green"
      />
      <StatCard
        title="COEs Totales"
        value={stats?.coes_total ?? 0}
        color="blue"
      />
      <StatCard
        title="Extracciones Exitosas"
        value={stats?.jobs_completed ?? 0}
        subtitle={`${stats?.jobs_failed ?? 0} fallidas`}
        color="green"
      />
      <StatCard
        title="En Proceso"
        value={(stats?.jobs_pending ?? 0) + (stats?.jobs_running ?? 0)}
        subtitle={stats?.jobs_running ? `${stats.jobs_running} ejecutando` : undefined}
        color="amber"
      />
    </div>
  );
}
```

**Step 2: Crear index.ts**

```tsx
export { StatsCards } from "./StatsCards";
```

**Step 3: Commit**

```bash
git add frontend/src/components/dashboard/
git commit -m "feat(ui): add StatsCards component for dashboard

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Crear componente PlaywrightPanel

**Files:**
- Create: `frontend/src/components/dashboard/PlaywrightPanel.tsx`
- Modify: `frontend/src/components/dashboard/index.ts`

**Step 1: Crear PlaywrightPanel.tsx**

```tsx
import { useState } from "react";
import { Button, Card, CardHeader, Input, Alert, Badge, Spinner } from "../ui";
import { useClientsQuery } from "../../hooks/useClients";
import { usePlaywrightJobQuery, useRunPlaywrightMutation } from "../../hooks/useClients";
import type { PlaywrightPipelineJob } from "../../clients";

function formatDate(date: Date): string {
  const day = date.getDate().toString().padStart(2, "0");
  const month = (date.getMonth() + 1).toString().padStart(2, "0");
  const year = date.getFullYear();
  return `${day}/${month}/${year}`;
}

function getDefaultDateRange() {
  const hasta = new Date();
  const desde = new Date();
  desde.setMonth(desde.getMonth() - 6);
  return {
    desde: desde.toISOString().split("T")[0],
    hasta: hasta.toISOString().split("T")[0],
  };
}

function JobStatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "success" | "warning" | "error" | "info"> = {
    pending: "warning",
    running: "info",
    completed: "success",
    failed: "error",
  };
  return <Badge variant={variants[status] ?? "default"}>{status}</Badge>;
}

export function PlaywrightPanel() {
  const defaults = getDefaultDateRange();
  const [fechaDesde, setFechaDesde] = useState(defaults.desde);
  const [fechaHasta, setFechaHasta] = useState(defaults.hasta);
  const [selectedClients, setSelectedClients] = useState<number[]>([]);
  const [currentJobId, setCurrentJobId] = useState<number | null>(null);

  const clientsQuery = useClientsQuery();
  const runMutation = useRunPlaywrightMutation();
  const jobQuery = usePlaywrightJobQuery(currentJobId);

  const activeClients = clientsQuery.data?.filter(
    (c) => c.activo && c.playwrightEnabled && c.claveFiscalCargada
  ) ?? [];

  const handleSelectAll = () => {
    if (selectedClients.length === activeClients.length) {
      setSelectedClients([]);
    } else {
      setSelectedClients(activeClients.map((c) => c.id));
    }
  };

  const handleToggleClient = (id: number) => {
    setSelectedClients((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleRun = async () => {
    if (selectedClients.length === 0) return;

    try {
      const result = await runMutation.mutateAsync({
        fechaDesde: formatDate(new Date(fechaDesde)),
        fechaHasta: formatDate(new Date(fechaHasta)),
        taxpayerIds: selectedClients,
      });
      setCurrentJobId(result.id);
    } catch {
      // Error handled by mutation
    }
  };

  const isRunning = jobQuery.data?.status === "pending" || jobQuery.data?.status === "running";
  const canRun = selectedClients.length > 0 && !runMutation.isPending && !isRunning;

  return (
    <Card padding="lg">
      <CardHeader
        title="Extracción de COEs"
        subtitle="Ejecutar Playwright para obtener COEs de AFIP"
      />

      <div className="space-y-4">
        {/* Fechas */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Fecha desde"
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            disabled={isRunning}
          />
          <Input
            label="Fecha hasta"
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            disabled={isRunning}
          />
        </div>

        {/* Selección de clientes */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-slate-700">
              Clientes ({selectedClients.length} de {activeClients.length} seleccionados)
            </label>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSelectAll}
              disabled={isRunning}
            >
              {selectedClients.length === activeClients.length ? "Deseleccionar todos" : "Seleccionar todos"}
            </Button>
          </div>

          {clientsQuery.isLoading ? (
            <div className="flex justify-center py-4">
              <Spinner />
            </div>
          ) : activeClients.length === 0 ? (
            <Alert variant="warning">
              No hay clientes configurados para Playwright
            </Alert>
          ) : (
            <div className="border border-slate-200 rounded-md max-h-48 overflow-y-auto">
              {activeClients.map((client) => (
                <label
                  key={client.id}
                  className="flex items-center px-3 py-2 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0"
                >
                  <input
                    type="checkbox"
                    checked={selectedClients.includes(client.id)}
                    onChange={() => handleToggleClient(client.id)}
                    disabled={isRunning}
                    className="h-4 w-4 text-green-600 rounded border-slate-300 focus:ring-green-500"
                  />
                  <span className="ml-3 text-sm text-slate-700">{client.empresa}</span>
                  <span className="ml-auto text-xs text-slate-400">{client.cuit}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Error */}
        {runMutation.isError ? (
          <Alert variant="error">
            {runMutation.error instanceof Error
              ? runMutation.error.message
              : "Error al iniciar extracción"}
          </Alert>
        ) : null}

        {/* Botón de ejecución */}
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={handleRun}
          disabled={!canRun}
          isLoading={runMutation.isPending}
        >
          {isRunning ? "Extracción en curso..." : "Iniciar Extracción"}
        </Button>

        {/* Estado del job */}
        {jobQuery.data ? (
          <div className="border-t border-slate-200 pt-4 mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-slate-700">Estado del Job</span>
              <JobStatusBadge status={jobQuery.data.status} />
            </div>

            {jobQuery.data.status === "running" && jobQuery.data.progress ? (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-slate-600">
                  <span>Progreso</span>
                  <span>
                    {jobQuery.data.progress.completedClients} / {jobQuery.data.progress.totalClients}
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-green-600 h-2 rounded-full transition-all"
                    style={{
                      width: `${
                        (jobQuery.data.progress.completedClients /
                          jobQuery.data.progress.totalClients) *
                        100
                      }%`,
                    }}
                  />
                </div>
              </div>
            ) : null}

            {jobQuery.data.status === "completed" && jobQuery.data.result ? (
              <div className="text-sm text-slate-600 space-y-1">
                <p>Clientes procesados: {jobQuery.data.result.taxpayersTotal}</p>
                <p className="text-green-600">Exitosos: {jobQuery.data.result.taxpayersOk}</p>
                {jobQuery.data.result.taxpayersError > 0 ? (
                  <p className="text-red-600">Con errores: {jobQuery.data.result.taxpayersError}</p>
                ) : null}
              </div>
            ) : null}

            {jobQuery.data.status === "failed" ? (
              <Alert variant="error">
                {jobQuery.data.errorMessage ?? "Error desconocido"}
              </Alert>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
```

**Step 2: Actualizar index.ts**

```tsx
export { StatsCards } from "./StatsCards";
export { PlaywrightPanel } from "./PlaywrightPanel";
```

**Step 3: Commit**

```bash
git add frontend/src/components/dashboard/
git commit -m "feat(ui): add PlaywrightPanel component for dashboard

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Crear componente RecentJobsPanel

**Files:**
- Create: `frontend/src/components/dashboard/RecentJobsPanel.tsx`
- Modify: `frontend/src/components/dashboard/index.ts`

**Step 1: Crear RecentJobsPanel.tsx**

```tsx
import { Card, CardHeader, Badge, Spinner } from "../ui";
import { useJobsQuery } from "../../hooks/useJobs";

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function JobStatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "success" | "warning" | "error" | "info"> = {
    pending: "warning",
    running: "info",
    completed: "success",
    failed: "error",
  };
  const labels: Record<string, string> = {
    pending: "Pendiente",
    running: "Ejecutando",
    completed: "Completado",
    failed: "Fallido",
  };
  return <Badge variant={variants[status] ?? "default"}>{labels[status] ?? status}</Badge>;
}

export function RecentJobsPanel() {
  const jobsQuery = useJobsQuery({ limit: 10 });

  return (
    <Card padding="lg">
      <CardHeader
        title="Extracciones Recientes"
        subtitle="Últimas 10 ejecuciones de Playwright"
      />

      {jobsQuery.isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : jobsQuery.data?.jobs.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">
          No hay extracciones registradas
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                <th className="text-left py-2 px-2 font-medium text-slate-600">ID</th>
                <th className="text-left py-2 px-2 font-medium text-slate-600">Fecha</th>
                <th className="text-left py-2 px-2 font-medium text-slate-600">Estado</th>
                <th className="text-left py-2 px-2 font-medium text-slate-600">Duración</th>
              </tr>
            </thead>
            <tbody>
              {jobsQuery.data?.jobs.map((job) => {
                const duration =
                  job.started_at && job.finished_at
                    ? Math.round(
                        (new Date(job.finished_at).getTime() -
                          new Date(job.started_at).getTime()) /
                          1000
                      )
                    : null;

                return (
                  <tr key={job.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-2 px-2 text-slate-900">#{job.id}</td>
                    <td className="py-2 px-2 text-slate-600">
                      {formatDate(job.created_at)}
                    </td>
                    <td className="py-2 px-2">
                      <JobStatusBadge status={job.status} />
                    </td>
                    <td className="py-2 px-2 text-slate-600">
                      {duration !== null ? `${duration}s` : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
```

**Step 2: Actualizar index.ts**

```tsx
export { StatsCards } from "./StatsCards";
export { PlaywrightPanel } from "./PlaywrightPanel";
export { RecentJobsPanel } from "./RecentJobsPanel";
```

**Step 3: Commit**

```bash
git add frontend/src/components/dashboard/
git commit -m "feat(ui): add RecentJobsPanel component for dashboard

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Actualizar HomePage con dashboard completo

**Files:**
- Modify: `frontend/src/pages/HomePage.tsx`

**Step 1: Reemplazar HomePage.tsx**

```tsx
import { useAuthStore } from "../store/useAuthStore";
import { useStatsQuery } from "../hooks/useStats";
import { StatsCards, PlaywrightPanel, RecentJobsPanel } from "../components/dashboard";

export function HomePage() {
  const { user } = useAuthStore();
  const statsQuery = useStatsQuery();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">
          Bienvenido, {user?.nombre}
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Panel de control del sistema de liquidación de granos
        </p>
      </div>

      {/* Stats Cards */}
      <StatsCards stats={statsQuery.data} isLoading={statsQuery.isLoading} />

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Panel de Playwright */}
        <PlaywrightPanel />

        {/* Jobs recientes */}
        <RecentJobsPanel />
      </div>
    </div>
  );
}
```

**Step 2: Verificar build**

Run: `cd frontend && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/pages/HomePage.tsx
git commit -m "feat(ui): update HomePage with complete dashboard

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Agregar hooks de Playwright faltantes

**Files:**
- Modify: `frontend/src/hooks/useClients.ts`

**Step 1: Verificar y agregar hooks faltantes**

Verificar que `useClients.ts` exporte:
- `useClientsQuery`
- `usePlaywrightJobQuery`
- `useRunPlaywrightMutation`

Si no existen, crearlos basándose en la funcionalidad existente en `clients.ts`.

**Step 2: Commit si hay cambios**

```bash
git add frontend/src/hooks/
git commit -m "feat(hooks): add missing Playwright hooks

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Ejecutar tests y verificar

**Step 1: Ejecutar tests de backend**

Run: `cd backend && pytest -v`

**Step 2: Verificar build de frontend**

Run: `cd frontend && npm run build`

**Step 3: Verificar TypeScript**

Run: `cd frontend && npx tsc --noEmit`

**Step 4: Corregir errores si los hay**

**Step 5: Commit final si hay cambios**

```bash
git add .
git commit -m "fix: resolve issues found during verification

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Push y crear PR

**Step 1: Push rama**

Run: `git push -u origin feature/004-home-dashboard`

**Step 2: Crear PR**

```bash
gh pr create --base dev --head feature/004-home-dashboard --title "feat: add Home Dashboard with stats and Playwright panel (Phase 2)" --body "$(cat <<'EOF'
## Summary
- New `/api/stats` endpoint for aggregated metrics
- Dashboard with stats cards (active clients, COEs, jobs)
- Playwright execution panel with client selection and date range
- Recent jobs history panel
- New UI components: Card, Badge, Select

## Backend Changes
- New `stats_bp` blueprint with `/api/stats` endpoint
- Returns counts for clients, jobs, COEs, and last job info

## Frontend Changes
- New components: Card, CardHeader, Badge, Select
- Dashboard components: StatsCards, PlaywrightPanel, RecentJobsPanel
- New API clients: stats.ts, jobs.ts
- New hooks: useStats, useJobs
- Updated HomePage with complete dashboard layout

## Test Plan
- [x] Integration tests for /stats endpoint
- [x] Frontend builds successfully
- [x] TypeScript compiles without errors
- [x] All backend tests pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
