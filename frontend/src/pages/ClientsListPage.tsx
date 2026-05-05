import { useState } from "react";
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
  Pagination,
  Dropdown,
  DropdownItem,
  DropdownDivider,
  ConfirmModal,
} from "../components/ui";
import {
  useClientsPaginatedQuery,
  useDeleteClientMutation,
  usePermanentDeleteClientMutation,
} from "../useClients";
import type { Client } from "../clients";

type DeleteAction = "deactivate" | "permanent";

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
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [pendingDelete, setPendingDelete] = useState<{
    client: Client;
    action: DeleteAction;
  } | null>(null);

  const clientsQuery = useClientsPaginatedQuery({
    page,
    per_page: 20,
    search: search || undefined,
  });
  const deactivateMutation = useDeleteClientMutation();
  const permanentDeleteMutation = usePermanentDeleteClientMutation();

  const clients = clientsQuery.data?.clients ?? [];
  const total = clientsQuery.data?.total ?? 0;

  const isDeleting =
    deactivateMutation.isPending || permanentDeleteMutation.isPending;
  const deleteError =
    pendingDelete?.action === "permanent"
      ? permanentDeleteMutation.error?.message
      : deactivateMutation.error?.message;

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(1);
  }

  function handleRequestDelete(client: Client) {
    const action: DeleteAction =
      client.coesCount === 0 ? "permanent" : "deactivate";
    deactivateMutation.reset();
    permanentDeleteMutation.reset();
    setPendingDelete({ client, action });
  }

  function handleClosePendingDelete() {
    if (isDeleting) return;
    setPendingDelete(null);
    deactivateMutation.reset();
    permanentDeleteMutation.reset();
  }

  async function handleConfirmDelete() {
    if (!pendingDelete) return;
    const { client, action } = pendingDelete;
    try {
      if (action === "permanent") {
        await permanentDeleteMutation.mutateAsync(client.id);
      } else {
        await deactivateMutation.mutateAsync(client.id);
      }
      setPendingDelete(null);
    } catch {
      // Mantener el modal abierto: error visible para el usuario
    }
  }

  return (
    <div>
      <PageHeader
        title="Clientes"
        subtitle={total > 0 ? `${total} ${total === 1 ? "cliente" : "clientes"}` : undefined}
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
            onChange={handleSearchChange}
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
        ) : clients.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            {search ? "No se encontraron clientes" : "No hay clientes registrados"}
          </div>
        ) : (
          <>
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
              {clients.map((client) => (
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
                      {client.coesCount === 0 ? (
                        <DropdownItem
                          variant="danger"
                          onClick={() => handleRequestDelete(client)}
                        >
                          Eliminar
                        </DropdownItem>
                      ) : (
                        <DropdownItem
                          variant="danger"
                          onClick={() => handleRequestDelete(client)}
                          disabled={!client.activo}
                        >
                          Desactivar
                        </DropdownItem>
                      )}
                    </Dropdown>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {clientsQuery.data ? (
            <Pagination
              page={clientsQuery.data.page}
              pages={clientsQuery.data.pages}
              total={clientsQuery.data.total}
              perPage={clientsQuery.data.per_page}
              onPageChange={setPage}
            />
          ) : null}
          </>
        )}
      </Card>

      <ConfirmModal
        isOpen={pendingDelete !== null}
        onClose={handleClosePendingDelete}
        onConfirm={handleConfirmDelete}
        title={
          pendingDelete?.action === "permanent"
            ? "Eliminar cliente"
            : "Desactivar cliente"
        }
        message={
          pendingDelete?.action === "permanent"
            ? `¿Eliminar permanentemente a ${pendingDelete.client.empresa}? Esta acción no se puede deshacer y borrará también sus certificados.`
            : `¿Desactivar a ${pendingDelete?.client.empresa}? El cliente quedará inactivo pero se conservará su historial de COEs.`
        }
        confirmLabel={
          pendingDelete?.action === "permanent" ? "Eliminar" : "Desactivar"
        }
        variant="danger"
        isLoading={isDeleting}
        errorMessage={deleteError}
      />
    </div>
  );
}
