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
