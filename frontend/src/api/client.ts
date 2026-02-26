const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:5001/api";

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("No se pudo consultar /health");
  return res.json();
}

async function postJson(path: string, body: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? "Error en solicitud");
  return data;
}

export async function wslpgDummy() {
  const res = await fetch(`${API_BASE}/wslpg/mvp/dummy`);
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? "Error en dummy");
  return data;
}

export async function wslpgUltimoNroOrden(ptoEmision: number) {
  return postJson("/wslpg/mvp/liquidacion-ultimo-nro-orden", { ptoEmision });
}

export async function wslpgLiquidacionXNroOrden(
  ptoEmision: number,
  nroOrden: number
) {
  return postJson("/wslpg/mvp/liquidacion-x-nro-orden", { ptoEmision, nroOrden });
}

export async function wslpgLiquidacionXCoe(coe: number, pdf: "S" | "N") {
  return postJson("/wslpg/mvp/liquidacion-x-coe", { coe, pdf });
}
