import { fetchWithAuth } from "./client";

export interface SchedulerConfig {
  taxpayer_id: number;
  activo: boolean;
  dias_semana: string[];
  hora_local: string | null;
  dias_extraccion: number;
  ultimo_scrape_ok: string | null;
  ultimo_scrape_error: string | null;
}

export interface SchedulerErrorReciente {
  taxpayer_id: number;
  empresa: string;
  ultimo_scrape_error: string;
  ultimo_scrape_error_en: string | null;
}

export interface SchedulerStatus {
  taxpayers_total: number;
  taxpayers_activos_en_scheduler: number;
  ultimo_scrape_global: string | null;
  con_error_reciente: SchedulerErrorReciente[];
}

export interface PatchSchedulerBody {
  activo?: boolean;
  dias_semana?: string[];
  hora_local?: string;
  dias_extraccion?: number;
}

export interface RunNowResponse {
  taxpayer_id: number;
  extraction_job_id: number;
  estado: string;
}

interface ApiErrorBody {
  error?: string;
  mensaje?: string;
  detalle?: Record<string, unknown>;
}

function parseApiError(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const body = payload as ApiErrorBody;
    if (typeof body.mensaje === "string" && body.mensaje.trim()) return body.mensaje;
    if (typeof body.error === "string" && body.error.trim()) return body.error;
  }
  return fallback;
}

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function getSchedulerStatus(): Promise<SchedulerStatus> {
  const res = await fetchWithAuth("/scheduler/status", { method: "GET" });
  const data = await readJson(res);
  if (!res.ok) {
    throw new Error(parseApiError(data, "Error al obtener estado del scheduler"));
  }
  return data as SchedulerStatus;
}

export async function patchTaxpayerScheduler(
  taxpayerId: number,
  body: PatchSchedulerBody,
): Promise<SchedulerConfig> {
  const res = await fetchWithAuth(`/taxpayers/${taxpayerId}/scheduler`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  const data = await readJson(res);
  if (!res.ok) {
    throw new Error(parseApiError(data, "Error al actualizar el scheduler"));
  }
  return data as SchedulerConfig;
}

export async function runSchedulerNow(taxpayerId: number): Promise<RunNowResponse> {
  const res = await fetchWithAuth(`/scheduler/run-now/${taxpayerId}`, {
    method: "POST",
  });
  const data = await readJson(res);
  if (!res.ok) {
    throw new Error(parseApiError(data, "Error al disparar el scheduler"));
  }
  return data as RunNowResponse;
}
