import { fetchWithAuth } from "./client";

// ---------------------------------------------------------------------------
// Manual WS load types
// ---------------------------------------------------------------------------

export interface ConsultManualCoeRequest {
  coe: string;
  taxpayer_id: number;
}

export interface CoePreview {
  tipo_documento: string;
  pto_emision: number | null;
  nro_orden: number | null;
  estado: string | null;
  raw_data: Record<string, unknown> | null;
}

export interface ConsultManualCoeResponse {
  preview: CoePreview;
  tipo_documento: "LPG" | "AJUSTE";
  duplicado: boolean;
  coe_id: number | null;
}

export interface CreateManualCoeRequest {
  coe: string;
  taxpayer_id: number;
}

// ---------------------------------------------------------------------------
// Existing types
// ---------------------------------------------------------------------------

export interface Coe {
  id: number;
  taxpayer_id: number;
  coe: string;
  pto_emision: number | null;
  nro_orden: number | null;
  estado: string | null;
  tipo_documento: string;
  fecha_liquidacion: string | null;
  created_at: string | null;
  raw_data: Record<string, unknown> | null;
  datos_limpios: Record<string, unknown> | null;
  coe_estado?: {
    estado: string;
    descargado_en: string | null;
    cargado_en: string | null;
    error_fase: string | null;
    error_mensaje: string | null;
  } | null;
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
  estado_ciclo?: string;
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
  if (params?.estado_ciclo) searchParams.set("estado_ciclo", params.estado_ciclo);
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

export async function downloadCoePdf(docId: number): Promise<Blob> {
  const res = await fetchWithAuth(`/coes/${docId}/pdf`, { method: "GET" });
  if (!res.ok) {
    const text = await res.text();
    let errorMsg = "No se pudo descargar el PDF";
    try {
      const json = JSON.parse(text);
      if (json.error) errorMsg = json.error;
    } catch { /* ignore */ }
    throw new Error(errorMsg);
  }
  return res.blob();
}

export async function consultManualCoe(
  payload: ConsultManualCoeRequest
): Promise<ConsultManualCoeResponse> {
  const res = await fetchWithAuth("/coes/consultar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al consultar COE");
  }
  return data;
}

export async function createManualCoe(
  payload: CreateManualCoeRequest
): Promise<Coe> {
  const res = await fetchWithAuth("/coes/manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    // 409 Conflict — attach coe_id if present for duplicate handling
    const err = new Error(data?.error ?? "Error al cargar COE") as Error & { coe_id?: number };
    if (data?.coe_id !== undefined) {
      err.coe_id = data.coe_id;
    }
    throw err;
  }
  return data;
}
