import { fetchWithAuth } from "./client";

export interface User {
  id: number;
  username: string;
  nombre: string;
  rol: "admin" | "usuario";
  activo: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface UsersListResponse {
  users: User[];
}

export interface CreateUserInput {
  username: string;
  nombre: string;
  password: string;
  rol?: "admin" | "usuario";
}

export interface UpdateUserInput {
  nombre?: string;
  rol?: "admin" | "usuario";
  activo?: boolean;
}

export async function listUsers(): Promise<UsersListResponse> {
  const res = await fetchWithAuth("/users");
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener usuarios");
  }
  return data;
}

export async function getUser(id: number): Promise<User> {
  const res = await fetchWithAuth(`/users/${id}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener usuario");
  }
  return data;
}

export async function createUser(input: CreateUserInput): Promise<User> {
  const res = await fetchWithAuth("/users", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al crear usuario");
  }
  return data;
}

export async function updateUser(id: number, input: UpdateUserInput): Promise<User> {
  const res = await fetchWithAuth(`/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al actualizar usuario");
  }
  return data;
}

export async function deleteUser(id: number): Promise<void> {
  const res = await fetchWithAuth(`/users/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data?.error ?? "Error al eliminar usuario");
  }
}

export async function resetPassword(id: number, newPassword: string): Promise<void> {
  const res = await fetchWithAuth(`/users/${id}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al resetear contraseña");
  }
}
