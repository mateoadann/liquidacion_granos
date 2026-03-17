import { fetchWithAuth } from "./client";

export interface PersonaInfo {
  cuit: string;
  razonSocial: string;
  domicilio: string;
  localidad: string;
  provincia: string;
  codigoPostal: string;
  condicionIva: string;
  tipoPersona: string;
  estadoClave: string;
}

export async function getPersona(cuit: string): Promise<PersonaInfo> {
  const res = await fetchWithAuth(`/padron/${cuit}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error consultando padrón");
  }
  return data;
}
