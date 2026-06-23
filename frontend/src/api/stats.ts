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

export interface MonthlyStats {
  mes: number;
  anio: number;
  coes_nuevos: number;
  coes_f1: number;
  coes_f2: number;
  coes_nl: number;
  extracciones_exitosas: number;
  extracciones_fallidas: number;
}

export async function getStats(): Promise<DashboardStats> {
  const res = await fetchWithAuth("/stats");
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener estadísticas");
  }
  return data;
}

export async function fetchMonthlyStats(mes: number, anio: number): Promise<MonthlyStats> {
  const res = await fetchWithAuth(`/stats/mensual?mes=${mes}&anio=${anio}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener estadísticas mensuales");
  }
  return data;
}
