import { useAuthStore } from "../store/useAuthStore";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

// Coalesced in-flight refresh: all concurrent 401s share a single promise.
let refreshPromise: Promise<string | null> | null = null;

/**
 * Attempt to refresh the access token using the stored refresh token.
 * Returns the new access token on success, or null if the refresh fails
 * (expired refresh token, revoked session, network error, etc.).
 *
 * Multiple concurrent callers share the same promise so only one
 * /auth/refresh request is ever in flight at a time.
 */
function ensureRefresh(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async (): Promise<string | null> => {
    const stored = sessionStorage.getItem("refresh_token");
    if (!stored) return null;
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: stored }),
      });
      if (!res.ok) return null;
      const data = (await res.json()) as { access_token: string };
      useAuthStore.getState().updateToken(data.access_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

function getAuthHeader(): string | null {
  const token = useAuthStore.getState().accessToken;
  return token ? `Bearer ${token}` : null;
}

function buildHeaders(options: RequestInit): Headers {
  const headers = new Headers(options.headers);

  const authHeader = getAuthHeader();
  if (authHeader && !headers.has("Authorization")) {
    headers.set("Authorization", authHeader);
  }

  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;

  // Para FormData, dejar que el browser seteé automáticamente el boundary
  if (isFormData) {
    if (headers.has("Content-Type")) {
      headers.delete("Content-Type");
    }
  } else if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return headers;
}

// Paths that must never trigger a refresh attempt (would cause recursion/loops).
const SKIP_REFRESH_PATHS = ["/auth/refresh", "/auth/login"];

export async function fetchWithAuth(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = buildHeaders(options);

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status !== 401) return res;

  const { isRestoring, clearAuth } = useAuthStore.getState();
  const isAuthPath = SKIP_REFRESH_PATHS.some((p) => path.startsWith(p));

  // During initial session restore, restoreSession() owns the refresh/auth
  // lifecycle. Don't evict a still-recoverable session from a racing request —
  // just surface the 401 and let the restore flow decide.
  if (isRestoring) {
    return res;
  }

  // Auth endpoints themselves must never trigger a refresh (would recurse).
  if (isAuthPath) {
    clearAuth();
    window.location.href = "/login";
    return res;
  }

  // Attempt a single refresh (coalesced with any concurrent 401s).
  const newToken = await ensureRefresh();
  if (!newToken) {
    clearAuth();
    window.location.href = "/login";
    return res;
  }

  // Retry the original request once with the refreshed token.
  const retryHeaders = buildHeaders(options);
  retryHeaders.set("Authorization", `Bearer ${newToken}`);
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: retryHeaders,
  });
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
