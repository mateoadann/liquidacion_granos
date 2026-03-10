import { useAuthStore } from "../store/useAuthStore";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:5001/api";

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export async function fetchWithAuth(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  // Si 401 y no estamos restaurando sesión, limpiar auth y redirigir
  if (res.status === 401 && !useAuthStore.getState().isRestoring) {
    useAuthStore.getState().clearAuth();
    window.location.href = "/login";
  }

  return res;
}

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("No se pudo consultar /health");
  return res.json();
}

async function postJson(path: string, body: Record<string, unknown>) {
  const res = await fetchWithAuth(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? "Error en solicitud");
  return data;
}

export async function wslpgDummy() {
  const res = await fetchWithAuth("/wslpg/mvp/dummy");
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
