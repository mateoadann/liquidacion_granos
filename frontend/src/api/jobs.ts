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

export async function getJob(id: number): Promise<Job> {
  const res = await fetchWithAuth(`/jobs/${id}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener job");
  }
  return data;
}
