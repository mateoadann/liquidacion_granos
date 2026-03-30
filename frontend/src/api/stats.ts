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
