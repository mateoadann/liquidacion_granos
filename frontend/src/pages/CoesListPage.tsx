import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatDateOnly } from "../dateUtils";
import { PageHeader } from "../components/layout";
import {
  Card,
  Badge,
  Spinner,
  Alert,
  SearchInput,
  Select,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  Pagination,
  Button,
} from "../components/ui";
import { useCoesQuery } from "../hooks/useCoes";
import { useClientsQuery } from "../useClients";

function EstadoBadge({ estado }: { estado: string | null }) {
  const variants: Record<string, "success" | "warning" | "error" | "default"> = {
    AC: "success",
    AN: "error",
    PE: "warning",
  };
  const labels: Record<string, string> = {
    AC: "Activo",
    AN: "Anulado",
    PE: "Pendiente",
  };
  return (
    <Badge variant={variants[estado ?? ""] ?? "default"}>
      {labels[estado ?? ""] ?? estado ?? "-"}
    </Badge>
  );
}

export function CoesListPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [taxpayerId, setTaxpayerId] = useState<number | undefined>();
  const [estado, setEstado] = useState<string>("");

  const clientsQuery = useClientsQuery();
  const coesQuery = useCoesQuery({
    page,
    per_page: 20,
    taxpayer_id: taxpayerId,
    estado: estado || undefined,
    search: search || undefined,
  });

  const clients = clientsQuery.data ?? [];

  function handleSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function handleTaxpayerChange(value: string) {
    setTaxpayerId(value ? Number(value) : undefined);
    setPage(1);
  }

  function handleEstadoChange(value: string) {
    setEstado(value);
    setPage(1);
  }

  return (
    <div>
      <PageHeader
        title="COEs"
        subtitle={coesQuery.data ? `${coesQuery.data.total} documentos` : undefined}
      />

      <Card padding="none">
        {/* Filtros */}
        <div className="p-4 border-b border-slate-200 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <SearchInput
              value={search}
              onChange={handleSearch}
              placeholder="Buscar por COE..."
            />
            <Select
              value={taxpayerId?.toString() ?? ""}
              onChange={(e) => handleTaxpayerChange(e.target.value)}
              options={[
                { value: "", label: "Todos los clientes" },
                ...clients.map((c) => ({ value: c.id.toString(), label: c.empresa })),
              ]}
            />
            <Select
              value={estado}
              onChange={(e) => handleEstadoChange(e.target.value)}
              options={[
                { value: "", label: "Todos los estados" },
                { value: "AC", label: "Activo" },
                { value: "AN", label: "Anulado" },
                { value: "PE", label: "Pendiente" },
              ]}
            />
          </div>
        </div>

        {/* Tabla */}
        {coesQuery.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : coesQuery.isError ? (
          <div className="p-4">
            <Alert variant="error">Error al cargar COEs</Alert>
          </div>
        ) : coesQuery.data?.coes.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            No se encontraron COEs
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableCell header>COE</TableCell>
                  <TableCell header>Cliente</TableCell>
                  <TableCell header>Fecha</TableCell>
                  <TableCell header>Estado</TableCell>
                  <TableCell header className="w-20"></TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coesQuery.data?.coes.map((coe) => {
                  const client = clients.find((c) => c.id === coe.taxpayer_id);
                  return (
                    <TableRow key={coe.id}>
                      <TableCell className="font-mono">{coe.coe ?? "-"}</TableCell>
                      <TableCell>{client?.empresa ?? `ID: ${coe.taxpayer_id}`}</TableCell>
                      <TableCell className="text-slate-600">
{formatDateOnly(coe.created_at)}
                      </TableCell>
                      <TableCell>
                        <EstadoBadge estado={coe.estado} />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => navigate(`/coes/${coe.id}`)}
                        >
                          Ver
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>

            {coesQuery.data ? (
              <Pagination
                page={coesQuery.data.page}
                pages={coesQuery.data.pages}
                total={coesQuery.data.total}
                perPage={coesQuery.data.per_page}
                onPageChange={setPage}
              />
            ) : null}
          </>
        )}
      </Card>
    </div>
  );
}
