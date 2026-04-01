const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: {
    id: number;
    username: string;
    nombre: string;
    rol: "admin" | "usuario";
  };
}

export interface RefreshResponse {
  access_token: string;
}

export async function login(data: LoginRequest): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  const json = await res.json();
  if (!res.ok) {
    throw new Error(json?.error ?? "Error al iniciar sesión");
  }

  return json;
}

export async function logout(accessToken: string): Promise<void> {
  const rt = sessionStorage.getItem("refresh_token");
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ refresh_token: rt ?? undefined }),
  });
}

export async function refreshToken(refreshTokenValue: string): Promise<RefreshResponse> {
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshTokenValue }),
  });

  const json = await res.json();
  if (!res.ok) {
    throw new Error(json?.error ?? "Error al renovar sesión");
  }

  return json;
}

export async function getMe(accessToken: string): Promise<LoginResponse["user"]> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  const json = await res.json();
  if (!res.ok) {
    throw new Error(json?.error ?? "Error al obtener usuario");
  }

  return json;
}
