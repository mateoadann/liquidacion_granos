import { fetchWithAuth } from "./client";

export type ExtractionHealthEstado = "verde" | "amarillo" | "rojo" | "gris";

export interface ClienteSalud {
  taxpayer_id: number;
  razon_social: string | null;
  cuit: string | null;
  estado: ExtractionHealthEstado;
  dias_sin_exito: number | null;
  ultima_ok: string | null;
  causa_codigo: string | null;
  causa_mensaje: string | null;
  es_accionable: boolean;
}

export interface ExtractionHealth {
  generado_en: string;
  resumen: Record<ExtractionHealthEstado, number>;
  clientes: ClienteSalud[];
}

export async function getExtractionHealth(): Promise<ExtractionHealth> {
  const res = await fetchWithAuth("/extracciones/salud");
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener la salud de extracciones");
  }
  return data;
}
