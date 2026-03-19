import { fetchWithAuth } from "./client";

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
