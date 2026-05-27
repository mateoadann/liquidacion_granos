import type { Client } from "../../clients";

export function normalizeClientQuery(raw: string): string {
  return raw.trim().toLowerCase();
}

export function matchesClientQuery(
  client: Pick<Client, "empresa" | "cuit" | "cuitRepresentado">,
  normalizedQuery: string,
): boolean {
  if (!normalizedQuery) return true;
  return (
    client.empresa.toLowerCase().includes(normalizedQuery) ||
    client.cuit.includes(normalizedQuery) ||
    client.cuitRepresentado.includes(normalizedQuery)
  );
}
