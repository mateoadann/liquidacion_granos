# Gestión de Clientes Mejorada - Plan de Implementación (Fase 3)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Mejorar la página de clientes con componentes Table, Modal y Dropdown reutilizables. Implementar navegación con React Router y página de detalle de cliente.

**Architecture:** Migrar ClientsPage a usar componentes UI del sistema de diseño. Implementar React Router para navegación entre páginas. Separar lógica en componentes más pequeños y reutilizables.

**Tech Stack:** React 18, React Router v6, TanStack Query, Tailwind CSS

---

## Task 1: Instalar React Router y configurar rutas

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/ClientsPage.tsx`
- Create: `frontend/src/components/layout/Layout.tsx`

**Step 1: Instalar react-router-dom**

```bash
cd frontend && npm install react-router-dom
```

**Step 2: Crear Layout.tsx**

```tsx
import { type ReactNode } from "react";
import { NavLink } from "react-router-dom";

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? "bg-green-50 text-green-700"
        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
    }`;

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center space-x-8">
              <span className="text-xl font-bold text-green-600">LiqGranos</span>
              <div className="flex space-x-1">
                <NavLink to="/" className={linkClass}>
                  Inicio
                </NavLink>
                <NavLink to="/clientes" className={linkClass}>
                  Clientes
                </NavLink>
              </div>
            </div>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
}
```

**Step 3: Actualizar App.tsx con React Router**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { HomePage } from "./pages/HomePage";
import ClientsPage from "./ClientsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/clientes" element={<ClientsPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

**Step 4: Verificar build**

```bash
cd frontend && npm run build
```

**Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(routing): add React Router and Layout component

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Crear componentes Table y Dropdown

**Files:**
- Create: `frontend/src/components/ui/Table.tsx`
- Create: `frontend/src/components/ui/Dropdown.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Crear Table.tsx**

```tsx
import { type ReactNode } from "react";

interface TableProps {
  children: ReactNode;
  className?: string;
}

export function Table({ children, className = "" }: TableProps) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full text-sm">{children}</table>
    </div>
  );
}

interface TableHeaderProps {
  children: ReactNode;
}

export function TableHeader({ children }: TableHeaderProps) {
  return (
    <thead className="bg-slate-50 border-b border-slate-200">
      {children}
    </thead>
  );
}

interface TableBodyProps {
  children: ReactNode;
}

export function TableBody({ children }: TableBodyProps) {
  return <tbody className="divide-y divide-slate-100">{children}</tbody>;
}

interface TableRowProps {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}

export function TableRow({ children, onClick, className = "" }: TableRowProps) {
  return (
    <tr
      className={`hover:bg-slate-50 ${onClick ? "cursor-pointer" : ""} ${className}`}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

interface TableCellProps {
  children: ReactNode;
  className?: string;
  header?: boolean;
}

export function TableCell({ children, className = "", header = false }: TableCellProps) {
  const baseClasses = "px-4 py-3 text-left";

  if (header) {
    return (
      <th className={`${baseClasses} font-medium text-slate-600 ${className}`}>
        {children}
      </th>
    );
  }

  return (
    <td className={`${baseClasses} text-slate-900 ${className}`}>
      {children}
    </td>
  );
}
```

**Step 2: Crear Dropdown.tsx**

```tsx
import { useState, useRef, useEffect, type ReactNode } from "react";

interface DropdownProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
}

export function Dropdown({ trigger, children, align = "right" }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={dropdownRef} className="relative inline-block">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className="p-1 rounded hover:bg-slate-100 transition-colors"
      >
        {trigger}
      </button>

      {isOpen ? (
        <div
          className={`
            absolute z-50 mt-1 w-48 py-1
            bg-white rounded-lg border border-slate-200 shadow-lg
            ${align === "right" ? "right-0" : "left-0"}
          `}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

interface DropdownItemProps {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "danger";
  disabled?: boolean;
}

export function DropdownItem({
  children,
  onClick,
  variant = "default",
  disabled = false,
}: DropdownItemProps) {
  const variantClasses = {
    default: "text-slate-700 hover:bg-slate-50",
    danger: "text-red-600 hover:bg-red-50",
  };

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      disabled={disabled}
      className={`
        w-full px-4 py-2 text-sm text-left
        ${variantClasses[variant]}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      {children}
    </button>
  );
}

export function DropdownDivider() {
  return <div className="my-1 border-t border-slate-100" />;
}
```

**Step 3: Actualizar index.ts**

```tsx
export { Button } from "./Button";
export { Input } from "./Input";
export { Alert } from "./Alert";
export { Spinner } from "./Spinner";
export { Card, CardHeader } from "./Card";
export { Badge } from "./Badge";
export { Select } from "./Select";
export { Table, TableHeader, TableBody, TableRow, TableCell } from "./Table";
export { Dropdown, DropdownItem, DropdownDivider } from "./Dropdown";
```

**Step 4: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(ui): add Table and Dropdown components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Crear componente Modal

**Files:**
- Create: `frontend/src/components/ui/Modal.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Crear Modal.tsx**

```tsx
import { useEffect, type ReactNode } from "react";
import { Button } from "./Button";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}

const sizeClasses = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
};

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  size = "md",
}: ModalProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
    }
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          className={`
            relative w-full ${sizeClasses[size]}
            bg-white rounded-lg shadow-xl
            transform transition-all
          `}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded hover:bg-slate-100 transition-colors"
            >
              <svg
                className="w-5 h-5 text-slate-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4">{children}</div>

          {/* Footer */}
          {footer ? (
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200">
              {footer}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "primary";
  isLoading?: boolean;
}

export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  variant = "primary",
  isLoading = false,
}: ConfirmModalProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            {cancelLabel}
          </Button>
          <Button
            variant={variant === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            isLoading={isLoading}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm text-slate-600">{message}</p>
    </Modal>
  );
}
```

**Step 2: Actualizar index.ts**

Agregar:
```tsx
export { Modal, ConfirmModal } from "./Modal";
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(ui): add Modal and ConfirmModal components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Crear componente PageHeader

**Files:**
- Create: `frontend/src/components/layout/PageHeader.tsx`
- Create: `frontend/src/components/layout/index.ts`

**Step 1: Crear PageHeader.tsx**

```tsx
import { type ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {subtitle ? (
          <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
    </div>
  );
}
```

**Step 2: Crear index.ts**

```tsx
export { Layout } from "./Layout";
export { PageHeader } from "./PageHeader";
```

**Step 3: Commit**

```bash
git add frontend/src/components/layout/
git commit -m "feat(layout): add PageHeader component

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Crear SearchInput component

**Files:**
- Create: `frontend/src/components/ui/SearchInput.tsx`
- Modify: `frontend/src/components/ui/index.ts`

**Step 1: Crear SearchInput.tsx**

```tsx
interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Buscar...",
  className = "",
}: SearchInputProps) {
  return (
    <div className={`relative ${className}`}>
      <svg
        className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
        />
      </svg>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="
          w-full pl-10 pr-4 py-2 rounded-lg border border-slate-300
          text-sm text-slate-900 placeholder:text-slate-400
          focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent
        "
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-slate-100"
        >
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      ) : null}
    </div>
  );
}
```

**Step 2: Actualizar index.ts**

Agregar:
```tsx
export { SearchInput } from "./SearchInput";
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/
git commit -m "feat(ui): add SearchInput component

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Refactorizar ClientsPage con nuevos componentes

**Files:**
- Create: `frontend/src/pages/ClientsListPage.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Crear ClientsListPage.tsx**

Este archivo usará los nuevos componentes UI para mostrar la lista de clientes de forma mejorada.

```tsx
import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import {
  Button,
  Card,
  Badge,
  Spinner,
  Alert,
  SearchInput,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  Dropdown,
  DropdownItem,
  DropdownDivider,
  ConfirmModal,
} from "../components/ui";
import {
  useClientsQuery,
  useDeleteClientMutation,
} from "../useClients";
import type { Client } from "../clients";

function ClientStatusBadge({ activo }: { activo: boolean }) {
  return (
    <Badge variant={activo ? "success" : "default"}>
      {activo ? "Activo" : "Inactivo"}
    </Badge>
  );
}

function MoreIcon() {
  return (
    <svg className="w-5 h-5 text-slate-500" fill="currentColor" viewBox="0 0 24 24">
      <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z" />
    </svg>
  );
}

export function ClientsListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [clientToDelete, setClientToDelete] = useState<Client | null>(null);

  const clientsQuery = useClientsQuery();
  const deleteMutation = useDeleteClientMutation();

  const clients = clientsQuery.data ?? [];

  const filteredClients = useMemo(() => {
    const trimmed = search.trim().toLowerCase();
    if (!trimmed) return clients;
    return clients.filter((client) => {
      const empresa = client.empresa.toLowerCase();
      const cuit = client.cuit.toLowerCase();
      return empresa.includes(trimmed) || cuit.includes(trimmed);
    });
  }, [clients, search]);

  async function handleDelete() {
    if (!clientToDelete) return;
    try {
      await deleteMutation.mutateAsync(clientToDelete.id);
      setClientToDelete(null);
    } catch {
      // Error manejado por mutation
    }
  }

  return (
    <div>
      <PageHeader
        title="Clientes"
        subtitle={`${clients.filter((c) => c.activo).length} activos de ${clients.length} totales`}
        actions={
          <Button onClick={() => navigate("/clientes/nuevo")}>
            Nuevo Cliente
          </Button>
        }
      />

      <Card>
        <div className="p-4 border-b border-slate-200">
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Buscar por empresa o CUIT..."
            className="max-w-sm"
          />
        </div>

        {clientsQuery.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : clientsQuery.isError ? (
          <div className="p-4">
            <Alert variant="error">Error al cargar clientes</Alert>
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            {search ? "No se encontraron clientes" : "No hay clientes registrados"}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableCell header>Empresa</TableCell>
                <TableCell header>CUIT</TableCell>
                <TableCell header>Estado</TableCell>
                <TableCell header>Config</TableCell>
                <TableCell header className="w-12"></TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredClients.map((client) => (
                <TableRow
                  key={client.id}
                  onClick={() => navigate(`/clientes/${client.id}`)}
                >
                  <TableCell className="font-medium">{client.empresa}</TableCell>
                  <TableCell className="font-mono text-slate-600">{client.cuit}</TableCell>
                  <TableCell>
                    <ClientStatusBadge activo={client.activo} />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {client.claveFiscalCargada ? (
                        <Badge variant="success" size="sm">Clave</Badge>
                      ) : (
                        <Badge variant="default" size="sm">Sin clave</Badge>
                      )}
                      {client.hasCertificates ? (
                        <Badge variant="success" size="sm">Cert</Badge>
                      ) : (
                        <Badge variant="default" size="sm">Sin cert</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Dropdown trigger={<MoreIcon />}>
                      <DropdownItem onClick={() => navigate(`/clientes/${client.id}`)}>
                        Ver detalle
                      </DropdownItem>
                      <DropdownItem onClick={() => navigate(`/clientes/${client.id}/editar`)}>
                        Editar
                      </DropdownItem>
                      <DropdownItem onClick={() => navigate(`/clientes/${client.id}/certificados`)}>
                        Certificados
                      </DropdownItem>
                      <DropdownDivider />
                      <DropdownItem
                        variant="danger"
                        onClick={() => setClientToDelete(client)}
                        disabled={!client.activo}
                      >
                        Desactivar
                      </DropdownItem>
                    </Dropdown>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <ConfirmModal
        isOpen={clientToDelete !== null}
        onClose={() => setClientToDelete(null)}
        onConfirm={handleDelete}
        title="Desactivar cliente"
        message={`¿Estás seguro de desactivar a ${clientToDelete?.empresa}?`}
        confirmLabel="Desactivar"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
```

**Step 2: Actualizar App.tsx**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { HomePage } from "./pages/HomePage";
import { ClientsListPage } from "./pages/ClientsListPage";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/clientes" element={<ClientsListPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

**Step 3: Verificar build**

```bash
cd frontend && npm run build
```

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(clientes): refactor clients list with new UI components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Crear página de detalle de cliente

**Files:**
- Create: `frontend/src/pages/ClientDetailPage.tsx`
- Create: `frontend/src/hooks/useClient.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Crear useClient.ts**

```tsx
import { useQuery } from "@tanstack/react-query";
import { getClient, type Client } from "../clients";

export function useClientQuery(id: number) {
  return useQuery<Client, Error>({
    queryKey: ["client", id],
    queryFn: () => getClient(id),
    enabled: id > 0,
  });
}
```

**Step 2: Crear ClientDetailPage.tsx**

```tsx
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, CardHeader, Badge, Button, Spinner, Alert } from "../components/ui";
import { useClientQuery } from "../hooks/useClient";

export function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const clientId = Number(id);

  const clientQuery = useClientQuery(clientId);
  const client = clientQuery.data;

  if (clientQuery.isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (clientQuery.isError || !client) {
    return (
      <div>
        <PageHeader title="Error" />
        <Alert variant="error">Cliente no encontrado</Alert>
        <Button variant="secondary" onClick={() => navigate("/clientes")} className="mt-4">
          Volver a clientes
        </Button>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={client.empresa}
        subtitle={`CUIT: ${client.cuit}`}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => navigate("/clientes")}>
              Volver
            </Button>
            <Button onClick={() => navigate(`/clientes/${client.id}/editar`)}>
              Editar
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Información General" />
          <dl className="space-y-4">
            <div>
              <dt className="text-sm font-medium text-slate-500">Estado</dt>
              <dd className="mt-1">
                <Badge variant={client.activo ? "success" : "default"}>
                  {client.activo ? "Activo" : "Inactivo"}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">CUIT Representado</dt>
              <dd className="mt-1 font-mono text-slate-900">{client.cuitRepresentado}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Ambiente</dt>
              <dd className="mt-1">
                <Badge variant={client.ambiente === "produccion" ? "success" : "warning"}>
                  {client.ambiente}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Playwright</dt>
              <dd className="mt-1">
                <Badge variant={client.playwrightEnabled ? "success" : "default"}>
                  {client.playwrightEnabled ? "Habilitado" : "Deshabilitado"}
                </Badge>
              </dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHeader title="Configuración" />
          <dl className="space-y-4">
            <div>
              <dt className="text-sm font-medium text-slate-500">Clave Fiscal</dt>
              <dd className="mt-1">
                <Badge variant={client.claveFiscalCargada ? "success" : "warning"}>
                  {client.claveFiscalCargada ? "Cargada" : "Sin cargar"}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Certificados</dt>
              <dd className="mt-1">
                {client.hasCertificates ? (
                  <div className="space-y-1">
                    <Badge variant="success">Certificados válidos</Badge>
                    {client.certificateInfo ? (
                      <p className="text-xs text-slate-500">
                        Vence: {client.certificateInfo.validTo}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <Badge variant="warning">Sin certificados</Badge>
                )}
              </dd>
            </div>
          </dl>

          <div className="mt-6 pt-4 border-t border-slate-200 flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(`/clientes/${client.id}/certificados`)}
            >
              Gestionar certificados
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
```

**Step 3: Actualizar App.tsx**

Agregar ruta:
```tsx
<Route path="/clientes/:id" element={<ClientDetailPage />} />
```

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(clientes): add client detail page

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Crear página de edición de cliente

**Files:**
- Create: `frontend/src/pages/ClientEditPage.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Crear ClientEditPage.tsx**

```tsx
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, Button, Input, Select, Alert, Spinner } from "../components/ui";
import { useClientQuery } from "../hooks/useClient";
import { useUpdateClientMutation, useCreateClientMutation } from "../useClients";
import { useState, useEffect } from "react";

interface FormData {
  empresa: string;
  cuit: string;
  cuitRepresentado: string;
  ambiente: "homologacion" | "produccion";
  activo: boolean;
  claveFiscal: string;
}

const initialForm: FormData = {
  empresa: "",
  cuit: "",
  cuitRepresentado: "",
  ambiente: "homologacion",
  activo: true,
  claveFiscal: "",
};

export function ClientEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === "nuevo";
  const clientId = isNew ? 0 : Number(id);

  const clientQuery = useClientQuery(clientId);
  const updateMutation = useUpdateClientMutation();
  const createMutation = useCreateClientMutation();

  const [form, setForm] = useState<FormData>(initialForm);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (clientQuery.data && !isNew) {
      setForm({
        empresa: clientQuery.data.empresa,
        cuit: clientQuery.data.cuit,
        cuitRepresentado: clientQuery.data.cuitRepresentado,
        ambiente: clientQuery.data.ambiente,
        activo: clientQuery.data.activo,
        claveFiscal: "",
      });
    }
  }, [clientQuery.data, isNew]);

  function handleChange(field: keyof FormData, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    try {
      if (isNew) {
        await createMutation.mutateAsync({
          empresa: form.empresa.trim(),
          cuit: form.cuit.trim(),
          cuit_representado: form.cuitRepresentado.trim(),
          ambiente: form.ambiente,
          activo: form.activo,
          clave_fiscal: form.claveFiscal.trim(),
        });
      } else {
        await updateMutation.mutateAsync({
          clientId,
          input: {
            empresa: form.empresa.trim(),
            cuit: form.cuit.trim(),
            cuit_representado: form.cuitRepresentado.trim(),
            ambiente: form.ambiente,
            activo: form.activo,
            ...(form.claveFiscal.trim() ? { clave_fiscal: form.claveFiscal.trim() } : {}),
          },
        });
      }
      navigate("/clientes");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al guardar");
    }
  }

  const isLoading = clientQuery.isLoading && !isNew;
  const isSaving = updateMutation.isPending || createMutation.isPending;

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={isNew ? "Nuevo Cliente" : "Editar Cliente"}
        subtitle={isNew ? undefined : form.empresa}
      />

      <Card className="max-w-2xl">
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error ? <Alert variant="error">{error}</Alert> : null}

          <Input
            label="Empresa"
            value={form.empresa}
            onChange={(e) => handleChange("empresa", e.target.value)}
            required
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="CUIT"
              value={form.cuit}
              onChange={(e) => handleChange("cuit", e.target.value)}
              placeholder="20123456789"
              required
            />
            <Input
              label="CUIT Representado"
              value={form.cuitRepresentado}
              onChange={(e) => handleChange("cuitRepresentado", e.target.value)}
              placeholder="20123456789"
              required
            />
          </div>

          <Select
            label="Ambiente"
            value={form.ambiente}
            onChange={(e) => handleChange("ambiente", e.target.value as "homologacion" | "produccion")}
            options={[
              { value: "homologacion", label: "Homologación" },
              { value: "produccion", label: "Producción" },
            ]}
          />

          <Input
            label={isNew ? "Clave Fiscal" : "Nueva Clave Fiscal (dejar vacío para mantener)"}
            type="password"
            value={form.claveFiscal}
            onChange={(e) => handleChange("claveFiscal", e.target.value)}
            required={isNew}
          />

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="activo"
              checked={form.activo}
              onChange={(e) => handleChange("activo", e.target.checked)}
              className="h-4 w-4 text-green-600 rounded border-slate-300"
            />
            <label htmlFor="activo" className="text-sm text-slate-700">
              Cliente activo
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <Button
              type="button"
              variant="secondary"
              onClick={() => navigate(-1)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button type="submit" isLoading={isSaving}>
              {isNew ? "Crear Cliente" : "Guardar Cambios"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
```

**Step 2: Actualizar App.tsx**

Agregar rutas:
```tsx
<Route path="/clientes/nuevo" element={<ClientEditPage />} />
<Route path="/clientes/:id/editar" element={<ClientEditPage />} />
```

**Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(clientes): add client edit/create page

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Tests y verificación final

**Step 1: Verificar TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

**Step 2: Verificar build**

```bash
cd frontend && npm run build
```

**Step 3: Ejecutar tests de backend**

```bash
cd backend && pytest -v
```

---

## Task 10: Push y crear PR

**Step 1: Push**

```bash
git push -u origin feature/005-clientes-ui
```

**Step 2: Crear PR**

```bash
gh pr create --base dev --title "feat(ui): Gestión de Clientes mejorada - Fase 3" --body "$(cat <<'EOF'
## Summary

- React Router para navegación entre páginas
- Componentes UI: Table, Modal, Dropdown, SearchInput, PageHeader
- Layout compartido con navbar
- Página de lista de clientes mejorada
- Página de detalle de cliente
- Página de edición/creación de cliente

## Test plan

- [ ] Frontend build exitoso (`npm run build`)
- [ ] Navegación entre Home y Clientes funciona
- [ ] Lista de clientes muestra datos correctamente
- [ ] Búsqueda filtra clientes
- [ ] Dropdown de acciones funciona
- [ ] Modal de confirmación para desactivar
- [ ] Detalle de cliente muestra información
- [ ] Edición de cliente guarda cambios
- [ ] Creación de nuevo cliente funciona

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
