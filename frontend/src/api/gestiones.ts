import { fetchWithAuth } from "./client";

export type GestionTipo =
  | "alta_cliente"
  | "alta_proveedor"
  | "mapeo_grano"
  | "alta_cuenta"
  | "cuenta_venta_grano"
  | "carga_inconsistente";

export type GestionEstado =
  | "pendiente"
  | "realizada"
  | "verificada"
  | "verificacion_fallida";

export interface Gestion {
  gestion_id: string;
  tipo: GestionTipo;
  cuit_empresa: string;
  razon_social: string | null;
  identificador: string;
  descripcion: string;
  datos_contexto: Record<string, unknown> | null;
  coes_afectados: string[];
  estado: GestionEstado;
  detectado_en: string;
  realizada_en: string | null;
  realizada_por: string | null;
  verificada_en: string | null;
  verificacion_detalle: string | null;
}

export interface GestionesListResponse {
  total: number;
  gestiones: Gestion[];
}

export interface GestionesListParams {
  estado?: GestionEstado;
  cuit_empresa?: string;
  desde?: string;
}

export async function listGestiones(
  params?: GestionesListParams,
): Promise<GestionesListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.estado) searchParams.set("estado", params.estado);
  if (params?.cuit_empresa) searchParams.set("cuit_empresa", params.cuit_empresa);
  if (params?.desde) searchParams.set("desde", params.desde);

  const query = searchParams.toString();
  const path = query ? `/v1/gestiones?${query}` : "/v1/gestiones";

  const res = await fetchWithAuth(path);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.mensaje ?? data?.error ?? "Error al obtener gestiones");
  }
  return data as GestionesListResponse;
}

export async function marcarGestionRealizada(gestionId: string): Promise<Gestion> {
  const res = await fetchWithAuth(`/v1/gestiones/${gestionId}/realizada`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.mensaje ?? data?.error ?? "No se pudo marcar la gestión");
  }
  return data as Gestion;
}
