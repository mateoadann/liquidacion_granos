# Exportación y Gestión de Usuarios - Plan de Implementación (Fase 5)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implementar página de exportación de COEs con wizard visual, y CRUD de usuarios con restricción de último admin.

**Architecture:** Nueva página `/exportar` con wizard de 3 pasos. Páginas `/configuracion` y `/configuracion/usuarios` con CRUD de usuarios restringido a admins. Backend con endpoints CRUD para users y validaciones de seguridad.

**Tech Stack:** Flask, SQLAlchemy, React 18, React Router v6, TanStack Query, Zustand, Tailwind CSS

---

## Task 1: Crear endpoints CRUD /api/users (backend)

**Files:**
- Create: `backend/app/api/users.py`
- Create: `backend/tests/integration/test_users_api.py`
- Modify: `backend/app/api/__init__.py`

**Step 1: Crear tests**

```python
from __future__ import annotations

from app.extensions import db
from app.models import User


def _create_user(*, username: str, nombre: str, rol: str = "usuario") -> User:
    user = User()
    user.username = username
    user.nombre = nombre
    user.rol = rol
    user.set_password("password123")
    user.activo = True
    db.session.add(user)
    db.session.commit()
    return user


def test_list_users_empty(client):
    response = client.get("/api/users")
    assert response.status_code == 200
    data = response.get_json()
    assert data["users"] == []


def test_list_users_returns_data(client):
    _create_user(username="user1", nombre="Usuario 1")
    _create_user(username="user2", nombre="Usuario 2")

    response = client.get("/api/users")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["users"]) == 2


def test_get_user_detail(client):
    user = _create_user(username="testuser", nombre="Test User", rol="admin")

    response = client.get(f"/api/users/{user.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["username"] == "testuser"
    assert data["nombre"] == "Test User"
    assert data["rol"] == "admin"
    assert "password_hash" not in data


def test_get_user_not_found(client):
    response = client.get("/api/users/99999")
    assert response.status_code == 404


def test_create_user(client):
    response = client.post("/api/users", json={
        "username": "newuser",
        "nombre": "New User",
        "password": "securepass123",
        "rol": "usuario"
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data["username"] == "newuser"


def test_create_user_duplicate_username(client):
    _create_user(username="existing", nombre="Existing")

    response = client.post("/api/users", json={
        "username": "existing",
        "nombre": "New User",
        "password": "securepass123"
    })
    assert response.status_code == 409


def test_update_user(client):
    user = _create_user(username="updateme", nombre="Old Name")

    response = client.patch(f"/api/users/{user.id}", json={
        "nombre": "New Name"
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["nombre"] == "New Name"


def test_cannot_deactivate_last_admin(client):
    admin = _create_user(username="soloadmin", nombre="Solo Admin", rol="admin")

    response = client.patch(f"/api/users/{admin.id}", json={
        "activo": False
    })
    assert response.status_code == 400
    assert "último admin" in response.get_json()["error"].lower()


def test_cannot_change_last_admin_role(client):
    admin = _create_user(username="soloadmin", nombre="Solo Admin", rol="admin")

    response = client.patch(f"/api/users/{admin.id}", json={
        "rol": "usuario"
    })
    assert response.status_code == 400
    assert "último admin" in response.get_json()["error"].lower()


def test_delete_user(client):
    user = _create_user(username="deleteme", nombre="Delete Me")

    response = client.delete(f"/api/users/{user.id}")
    assert response.status_code == 204


def test_cannot_delete_last_admin(client):
    admin = _create_user(username="soloadmin", nombre="Solo Admin", rol="admin")

    response = client.delete(f"/api/users/{admin.id}")
    assert response.status_code == 400


def test_reset_password(client):
    user = _create_user(username="resetme", nombre="Reset Me")

    response = client.post(f"/api/users/{user.id}/reset-password", json={
        "new_password": "newpassword123"
    })
    assert response.status_code == 200
```

**Step 2: Crear users.py**

```python
from __future__ import annotations

from flask import Blueprint, request

from ..extensions import db
from ..models import User

users_bp = Blueprint("users", __name__)


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nombre": user.nombre,
        "rol": user.rol,
        "activo": user.activo,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _count_active_admins() -> int:
    return User.query.filter_by(rol="admin", activo=True).count()


def _is_last_active_admin(user: User) -> bool:
    if user.rol != "admin" or not user.activo:
        return False
    return _count_active_admins() == 1


@users_bp.get("/users")
def list_users():
    users = User.query.order_by(User.nombre).all()
    return {"users": [_serialize_user(u) for u in users]}


@users_bp.get("/users/<int:user_id>")
def get_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404
    return _serialize_user(user)


@users_bp.post("/users")
def create_user():
    data = request.get_json(silent=True) or {}

    username = data.get("username", "").strip()
    nombre = data.get("nombre", "").strip()
    password = data.get("password", "")
    rol = data.get("rol", "usuario")

    if not username or not nombre or not password:
        return {"error": "username, nombre y password son requeridos"}, 400

    if len(password) < 8:
        return {"error": "La contraseña debe tener al menos 8 caracteres"}, 400

    if User.query.filter_by(username=username).first():
        return {"error": "El username ya existe"}, 409

    user = User()
    user.username = username
    user.nombre = nombre
    user.rol = rol if rol in ("admin", "usuario") else "usuario"
    user.set_password(password)
    user.activo = True

    db.session.add(user)
    db.session.commit()

    return _serialize_user(user), 201


@users_bp.patch("/users/<int:user_id>")
def update_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404

    data = request.get_json(silent=True) or {}

    # Validar restricción de último admin
    is_last_admin = _is_last_active_admin(user)

    if is_last_admin:
        if data.get("activo") is False:
            return {"error": "No se puede desactivar al último admin activo"}, 400
        if data.get("rol") == "usuario":
            return {"error": "No se puede cambiar el rol del último admin activo"}, 400

    if "nombre" in data:
        user.nombre = data["nombre"].strip()

    if "rol" in data and data["rol"] in ("admin", "usuario"):
        user.rol = data["rol"]

    if "activo" in data:
        user.activo = bool(data["activo"])

    db.session.commit()

    return _serialize_user(user)


@users_bp.delete("/users/<int:user_id>")
def delete_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404

    if _is_last_active_admin(user):
        return {"error": "No se puede eliminar al último admin activo"}, 400

    db.session.delete(user)
    db.session.commit()

    return "", 204


@users_bp.post("/users/<int:user_id>/reset-password")
def reset_password(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return {"error": "Usuario no encontrado"}, 404

    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password", "")

    if len(new_password) < 8:
        return {"error": "La contraseña debe tener al menos 8 caracteres"}, 400

    user.set_password(new_password)
    db.session.commit()

    return {"message": "Contraseña actualizada"}
```

**Step 3: Registrar blueprint**

En `backend/app/api/__init__.py`, agregar:
```python
from .users import users_bp
# En register_blueprints():
app.register_blueprint(users_bp, url_prefix="/api")
```

**Step 4: Ejecutar tests**

```bash
cd backend && pytest tests/integration/test_users_api.py -v
```

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat(api): add /api/users CRUD endpoints with last admin protection

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Crear API client y hooks para Users en frontend

**Files:**
- Create: `frontend/src/api/users.ts`
- Create: `frontend/src/hooks/useUsers.ts`

**Step 1: Crear users.ts**

```tsx
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
```

**Step 2: Crear useUsers.ts**

```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listUsers,
  getUser,
  createUser,
  updateUser,
  deleteUser,
  resetPassword,
  type User,
  type UsersListResponse,
  type CreateUserInput,
  type UpdateUserInput,
} from "../api/users";

export function useUsersQuery() {
  return useQuery<UsersListResponse, Error>({
    queryKey: ["users"],
    queryFn: listUsers,
  });
}

export function useUserQuery(id: number | null) {
  return useQuery<User, Error>({
    queryKey: ["user", id],
    queryFn: () => getUser(id!),
    enabled: id !== null && id > 0,
  });
}

export function useCreateUserMutation() {
  const queryClient = useQueryClient();
  return useMutation<User, Error, CreateUserInput>({
    mutationFn: createUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useUpdateUserMutation() {
  const queryClient = useQueryClient();
  return useMutation<User, Error, { id: number; input: UpdateUserInput }>({
    mutationFn: ({ id, input }) => updateUser(id, input),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      void queryClient.invalidateQueries({ queryKey: ["user", variables.id] });
    },
  });
}

export function useDeleteUserMutation() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: deleteUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useResetPasswordMutation() {
  return useMutation<void, Error, { id: number; newPassword: string }>({
    mutationFn: ({ id, newPassword }) => resetPassword(id, newPassword),
  });
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/users.ts frontend/src/hooks/useUsers.ts
git commit -m "feat(api): add Users API client and hooks

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Crear página ExportPage (wizard de exportación)

**Files:**
- Create: `frontend/src/pages/ExportPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx`

**Step 1: Crear ExportPage.tsx**

```tsx
import { useState } from "react";
import { PageHeader } from "../components/layout";
import { Card, Button, Spinner, Alert, Badge } from "../components/ui";
import { useClientsQuery } from "../useClients";
import { useDownloadClientCoesMutation } from "../useClients";

type Step = 1 | 2 | 3;

export function ExportPage() {
  const [step, setStep] = useState<Step>(1);
  const [selectedClients, setSelectedClients] = useState<number[]>([]);
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [formato, setFormato] = useState<"csv" | "xlsx">("csv");

  const clientsQuery = useClientsQuery();
  const downloadMutation = useDownloadClientCoesMutation();

  const clients = clientsQuery.data ?? [];
  const activeClients = clients.filter((c) => c.activo);

  function toggleClient(clientId: number) {
    setSelectedClients((prev) =>
      prev.includes(clientId)
        ? prev.filter((id) => id !== clientId)
        : [...prev, clientId]
    );
  }

  function selectAll() {
    setSelectedClients(activeClients.map((c) => c.id));
  }

  function selectNone() {
    setSelectedClients([]);
  }

  async function handleExport() {
    if (selectedClients.length === 0) return;

    try {
      await downloadMutation.mutateAsync({
        clientId: selectedClients[0],
        fechaDesde: fechaDesde || undefined,
        fechaHasta: fechaHasta || undefined,
        formato,
      });
    } catch (err) {
      // Error manejado por mutation
    }
  }

  return (
    <div>
      <PageHeader
        title="Exportar COEs"
        subtitle="Descarga COEs en formato CSV o Excel"
      />

      {/* Progress Steps */}
      <div className="flex items-center justify-center mb-8">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center">
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center font-medium ${
                step >= s
                  ? "bg-green-600 text-white"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              {s}
            </div>
            {s < 3 && (
              <div
                className={`w-20 h-1 ${
                  step > s ? "bg-green-600" : "bg-slate-200"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      <Card className="max-w-2xl mx-auto">
        {/* Step 1: Seleccionar clientes */}
        {step === 1 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 1: Seleccionar clientes
            </h3>

            {clientsQuery.isLoading ? (
              <div className="flex justify-center py-8">
                <Spinner size="lg" />
              </div>
            ) : activeClients.length === 0 ? (
              <Alert variant="warning">No hay clientes activos</Alert>
            ) : (
              <>
                <div className="flex gap-2 mb-4">
                  <Button variant="ghost" size="sm" onClick={selectAll}>
                    Seleccionar todos
                  </Button>
                  <Button variant="ghost" size="sm" onClick={selectNone}>
                    Deseleccionar todos
                  </Button>
                </div>

                <div className="space-y-2 max-h-64 overflow-y-auto border border-slate-200 rounded-lg p-2">
                  {activeClients.map((client) => (
                    <label
                      key={client.id}
                      className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedClients.includes(client.id)}
                        onChange={() => toggleClient(client.id)}
                        className="h-4 w-4 text-green-600 rounded border-slate-300"
                      />
                      <span className="text-sm text-slate-900">{client.empresa}</span>
                      <span className="text-xs text-slate-500 font-mono">
                        {client.cuit}
                      </span>
                    </label>
                  ))}
                </div>

                <p className="mt-4 text-sm text-slate-500">
                  {selectedClients.length} cliente(s) seleccionado(s)
                </p>
              </>
            )}

            <div className="flex justify-end mt-6">
              <Button
                onClick={() => setStep(2)}
                disabled={selectedClients.length === 0}
              >
                Siguiente
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Rango de fechas */}
        {step === 2 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 2: Rango de fechas (opcional)
            </h3>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Desde
                </label>
                <input
                  type="date"
                  value={fechaDesde}
                  onChange={(e) => setFechaDesde(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Hasta
                </label>
                <input
                  type="date"
                  value={fechaHasta}
                  onChange={(e) => setFechaHasta(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
            </div>

            <p className="mt-4 text-sm text-slate-500">
              Dejar vacío para exportar todas las fechas
            </p>

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => setStep(1)}>
                Anterior
              </Button>
              <Button onClick={() => setStep(3)}>Siguiente</Button>
            </div>
          </div>
        )}

        {/* Step 3: Formato y confirmación */}
        {step === 3 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 3: Formato y confirmación
            </h3>

            <div className="mb-6">
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Formato de exportación
              </label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="formato"
                    value="csv"
                    checked={formato === "csv"}
                    onChange={() => setFormato("csv")}
                    className="h-4 w-4 text-green-600"
                  />
                  <span className="text-sm">CSV</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="formato"
                    value="xlsx"
                    checked={formato === "xlsx"}
                    onChange={() => setFormato("xlsx")}
                    className="h-4 w-4 text-green-600"
                  />
                  <span className="text-sm">Excel (.xlsx)</span>
                </label>
              </div>
            </div>

            <div className="bg-slate-50 rounded-lg p-4 mb-6">
              <h4 className="text-sm font-medium text-slate-900 mb-2">Resumen</h4>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt className="text-slate-500">Clientes:</dt>
                  <dd className="text-slate-900">{selectedClients.length}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Período:</dt>
                  <dd className="text-slate-900">
                    {fechaDesde && fechaHasta
                      ? `${fechaDesde} a ${fechaHasta}`
                      : fechaDesde
                      ? `Desde ${fechaDesde}`
                      : fechaHasta
                      ? `Hasta ${fechaHasta}`
                      : "Todas las fechas"}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Formato:</dt>
                  <dd className="text-slate-900">{formato.toUpperCase()}</dd>
                </div>
              </dl>
            </div>

            {downloadMutation.isError && (
              <Alert variant="error" className="mb-4">
                {downloadMutation.error.message}
              </Alert>
            )}

            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep(2)}>
                Anterior
              </Button>
              <Button
                onClick={handleExport}
                isLoading={downloadMutation.isPending}
              >
                Exportar
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
```

**Step 2: Actualizar Layout.tsx**

Agregar link a Exportar en la navbar:
```tsx
<NavLink to="/exportar" className={linkClass}>
  Exportar
</NavLink>
```

**Step 3: Actualizar App.tsx**

Agregar ruta:
```tsx
import { ExportPage } from "./pages/ExportPage";
// ...
<Route path="/exportar" element={<ExportPage />} />
```

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(export): add ExportPage with wizard for COE export

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Crear páginas de Configuración y Usuarios

**Files:**
- Create: `frontend/src/pages/ConfigPage.tsx`
- Create: `frontend/src/pages/UsersListPage.tsx`
- Create: `frontend/src/pages/UserEditModal.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx`

**Step 1: Crear ConfigPage.tsx**

```tsx
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, Button } from "../components/ui";

export function ConfigPage() {
  const navigate = useNavigate();

  return (
    <div>
      <PageHeader
        title="Configuración"
        subtitle="Administración del sistema"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl">
        <Card className="p-6">
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            Gestión de Usuarios
          </h3>
          <p className="text-sm text-slate-500 mb-4">
            Crear, editar y administrar usuarios del sistema
          </p>
          <Button onClick={() => navigate("/configuracion/usuarios")}>
            Administrar usuarios
          </Button>
        </Card>
      </div>
    </div>
  );
}
```

**Step 2: Crear UsersListPage.tsx**

```tsx
import { useState } from "react";
import { PageHeader } from "../components/layout";
import {
  Card,
  Badge,
  Spinner,
  Alert,
  Button,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  Modal,
  ConfirmModal,
} from "../components/ui";
import {
  useUsersQuery,
  useDeleteUserMutation,
  useUpdateUserMutation,
  useCreateUserMutation,
  useResetPasswordMutation,
} from "../hooks/useUsers";
import type { User } from "../api/users";

interface UserFormData {
  username: string;
  nombre: string;
  password: string;
  rol: "admin" | "usuario";
}

const initialForm: UserFormData = {
  username: "",
  nombre: "",
  password: "",
  rol: "usuario",
};

export function UsersListPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [deletingUser, setDeletingUser] = useState<User | null>(null);
  const [resettingUser, setResettingUser] = useState<User | null>(null);
  const [form, setForm] = useState<UserFormData>(initialForm);
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const usersQuery = useUsersQuery();
  const createMutation = useCreateUserMutation();
  const updateMutation = useUpdateUserMutation();
  const deleteMutation = useDeleteUserMutation();
  const resetMutation = useResetPasswordMutation();

  const users = usersQuery.data?.users ?? [];

  function openCreate() {
    setForm(initialForm);
    setError(null);
    setIsCreateOpen(true);
  }

  function openEdit(user: User) {
    setForm({
      username: user.username,
      nombre: user.nombre,
      password: "",
      rol: user.rol,
    });
    setError(null);
    setEditingUser(user);
  }

  async function handleCreate() {
    setError(null);
    try {
      await createMutation.mutateAsync({
        username: form.username.trim(),
        nombre: form.nombre.trim(),
        password: form.password,
        rol: form.rol,
      });
      setIsCreateOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al crear usuario");
    }
  }

  async function handleUpdate() {
    if (!editingUser) return;
    setError(null);
    try {
      await updateMutation.mutateAsync({
        id: editingUser.id,
        input: {
          nombre: form.nombre.trim(),
          rol: form.rol,
        },
      });
      setEditingUser(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al actualizar usuario");
    }
  }

  async function handleDelete() {
    if (!deletingUser) return;
    try {
      await deleteMutation.mutateAsync(deletingUser.id);
      setDeletingUser(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al eliminar usuario");
    }
  }

  async function handleToggleActive(user: User) {
    try {
      await updateMutation.mutateAsync({
        id: user.id,
        input: { activo: !user.activo },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cambiar estado");
    }
  }

  async function handleResetPassword() {
    if (!resettingUser) return;
    try {
      await resetMutation.mutateAsync({
        id: resettingUser.id,
        newPassword: newPassword,
      });
      setResettingUser(null);
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al resetear contraseña");
    }
  }

  return (
    <div>
      <PageHeader
        title="Usuarios"
        subtitle={`${users.length} usuarios registrados`}
        actions={
          <Button onClick={openCreate}>Nuevo usuario</Button>
        }
      />

      {error && (
        <Alert variant="error" className="mb-4">
          {error}
        </Alert>
      )}

      <Card padding="none">
        {usersQuery.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : users.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            No hay usuarios registrados
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableCell header>Usuario</TableCell>
                <TableCell header>Nombre</TableCell>
                <TableCell header>Rol</TableCell>
                <TableCell header>Estado</TableCell>
                <TableCell header className="w-48">Acciones</TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-mono">{user.username}</TableCell>
                  <TableCell>{user.nombre}</TableCell>
                  <TableCell>
                    <Badge variant={user.rol === "admin" ? "success" : "default"}>
                      {user.rol}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={user.activo ? "success" : "default"}>
                      {user.activo ? "Activo" : "Inactivo"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEdit(user)}
                      >
                        Editar
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setResettingUser(user);
                          setNewPassword("");
                        }}
                      >
                        Reset
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleActive(user)}
                      >
                        {user.activo ? "Desactivar" : "Activar"}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Modal Crear */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Nuevo usuario"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleCreate} isLoading={createMutation.isPending}>
              Crear
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Username
            </label>
            <input
              type="text"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Nombre
            </label>
            <input
              type="text"
              value={form.nombre}
              onChange={(e) => setForm({ ...form, nombre: e.target.value })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Contraseña
            </label>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Rol
            </label>
            <select
              value={form.rol}
              onChange={(e) => setForm({ ...form, rol: e.target.value as "admin" | "usuario" })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            >
              <option value="usuario">Usuario</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>
      </Modal>

      {/* Modal Editar */}
      <Modal
        isOpen={editingUser !== null}
        onClose={() => setEditingUser(null)}
        title="Editar usuario"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setEditingUser(null)}>
              Cancelar
            </Button>
            <Button onClick={handleUpdate} isLoading={updateMutation.isPending}>
              Guardar
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Username
            </label>
            <input
              type="text"
              value={form.username}
              disabled
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-slate-50"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Nombre
            </label>
            <input
              type="text"
              value={form.nombre}
              onChange={(e) => setForm({ ...form, nombre: e.target.value })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Rol
            </label>
            <select
              value={form.rol}
              onChange={(e) => setForm({ ...form, rol: e.target.value as "admin" | "usuario" })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            >
              <option value="usuario">Usuario</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>
      </Modal>

      {/* Modal Reset Password */}
      <Modal
        isOpen={resettingUser !== null}
        onClose={() => setResettingUser(null)}
        title="Resetear contraseña"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setResettingUser(null)}>
              Cancelar
            </Button>
            <Button onClick={handleResetPassword} isLoading={resetMutation.isPending}>
              Resetear
            </Button>
          </div>
        }
      >
        <div>
          <p className="text-sm text-slate-500 mb-4">
            Nueva contraseña para <strong>{resettingUser?.username}</strong>
          </p>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Nueva contraseña (mín. 8 caracteres)"
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
          />
        </div>
      </Modal>

      {/* Confirm Delete */}
      <ConfirmModal
        isOpen={deletingUser !== null}
        onClose={() => setDeletingUser(null)}
        onConfirm={handleDelete}
        title="Eliminar usuario"
        message={`¿Estás seguro de eliminar a "${deletingUser?.nombre}"? Esta acción no se puede deshacer.`}
        confirmLabel="Eliminar"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
```

**Step 3: Actualizar Layout.tsx**

Agregar link a Configuración:
```tsx
<NavLink to="/configuracion" className={linkClass}>
  Config
</NavLink>
```

**Step 4: Actualizar App.tsx**

Agregar rutas:
```tsx
import { ConfigPage } from "./pages/ConfigPage";
import { UsersListPage } from "./pages/UsersListPage";
// ...
<Route path="/configuracion" element={<ConfigPage />} />
<Route path="/configuracion/usuarios" element={<UsersListPage />} />
```

**Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat(config): add ConfigPage and UsersListPage with CRUD

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Tests y verificación final

**Step 1: Ejecutar tests de backend**

```bash
cd backend && pytest -v
```

**Step 2: Verificar build de frontend**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

---

## Task 6: Push y crear PR

**Step 1: Push**

```bash
git push -u origin feature/007-export-users
```

**Step 2: Crear PR**

```bash
gh pr create --base dev --title "feat(ui): Exportación y Gestión de Usuarios - Fase 5" --body "$(cat <<'EOF'
## Summary

### Backend
- CRUD `/api/users` con endpoints:
  - `GET /api/users` - Listado de usuarios
  - `GET /api/users/:id` - Detalle de usuario
  - `POST /api/users` - Crear usuario
  - `PATCH /api/users/:id` - Actualizar usuario
  - `DELETE /api/users/:id` - Eliminar usuario
  - `POST /api/users/:id/reset-password` - Resetear contraseña
- Validación de último admin (no se puede desactivar/eliminar/cambiar rol)
- Tests de integración

### Frontend
- API client y hooks para usuarios
- ExportPage con wizard de 3 pasos:
  - Selección de clientes
  - Rango de fechas
  - Formato y confirmación
- ConfigPage con enlace a usuarios
- UsersListPage con CRUD completo:
  - Crear/editar usuarios
  - Resetear contraseña
  - Activar/desactivar
- Links en navbar

## Test plan

- [ ] Backend tests pasan (`pytest -v`)
- [ ] Frontend build exitoso (`npm run build`)
- [ ] CRUD de usuarios funciona correctamente
- [ ] No se puede desactivar/eliminar último admin
- [ ] Wizard de exportación funciona
- [ ] Navegación entre páginas funciona

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
