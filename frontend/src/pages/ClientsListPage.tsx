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

      <Card padding="none">
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
                      {client.certificadosCargados ? (
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
