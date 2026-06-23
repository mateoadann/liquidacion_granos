import { fetchWithAuth } from "./client";

export const OPERATION_LABELS: Record<string, string> = {
  scheduler_lpg_extract: "Extracción automática",
  scheduler_lpg_extract_retry: "Reintento automático",
  scheduler_run_now: "Extracción programada (ejecutada ahora)",
  playwright_lpg_run: "Extracción manual",
  coe_carga_manual: "Carga manual de COE",
};

/** Returns the friendly label for an operation, or the raw string if unknown. */
export function operationLabel(op: string): string {
  return OPERATION_LABELS[op] ?? op;
}

export interface Job {
  id: number;
  taxpayer_id: number | null;
  operation: string;
  status: "pending" | "running" | "completed" | "failed" | "partial";
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  coe_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  current_phase: string | null;
  current_message: string | null;
  failure_phase: string | null;
  failure_message_user: string | null;
  failure_message_technical: string | null;
  failure_error_type: string | null;
}

export interface JobsListResponse {
  jobs: Job[];
  total: number;
}

export interface JobsPaginatedResponse {
  jobs: Job[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

function normalizeJobsListResponse(data: unknown): JobsListResponse {
  if (Array.isArray(data)) {
    return {
      jobs: data as Job[],
      total: data.length,
    };
  }

  if (data && typeof data === "object") {
    const parsed = data as { jobs?: unknown; total?: unknown };
    if (Array.isArray(parsed.jobs)) {
      return {
        jobs: parsed.jobs as Job[],
        total: typeof parsed.total === "number" ? parsed.total : parsed.jobs.length,
      };
    }
  }

  throw new Error("Formato de respuesta inválido al obtener jobs");
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

  return normalizeJobsListResponse(data);
}

export async function listJobsPaginated(params: {
  page: number;
  per_page?: number;
  status?: string;
  taxpayer_id?: number;
}): Promise<JobsPaginatedResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("page", params.page.toString());
  if (params.per_page) searchParams.set("per_page", params.per_page.toString());
  if (params.status) searchParams.set("status", params.status);
  if (params.taxpayer_id !== undefined) {
    searchParams.set("taxpayer_id", params.taxpayer_id.toString());
  }

  const res = await fetchWithAuth(`/jobs?${searchParams.toString()}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener jobs");
  }
  return data as JobsPaginatedResponse;
}

export async function retryJob(id: number): Promise<Job> {
  const res = await fetchWithAuth(`/playwright/lpg/jobs/${id}/retry`, {
    method: "POST",
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al reintentar el job");
  }
  return data.job as Job;
}

export async function getJob(id: number): Promise<Job> {
  const res = await fetchWithAuth(`/jobs/${id}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener job");
  }
  return data;
}
