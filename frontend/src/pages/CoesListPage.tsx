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
import { downloadCoePdf } from "../api/coes";

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
  const [downloadingPdfId, setDownloadingPdfId] = useState<number | null>(null);

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

  async function handleDownloadPdf(docId: number, coe: string) {
    setDownloadingPdfId(docId);
    try {
      const blob = await downloadCoePdf(docId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `liquidacion_${coe}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Error al descargar PDF");
    } finally {
      setDownloadingPdfId(null);
    }
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
                  <TableCell header>Tipo</TableCell>
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
                      <TableCell>
                        {coe.tipo_documento === "AJUSTE" ? (
                          <Badge variant="warning">Ajuste</Badge>
                        ) : (
                          <Badge variant="default">Liquidacion</Badge>
                        )}
                      </TableCell>
                      <TableCell>{client?.empresa ?? `ID: ${coe.taxpayer_id}`}</TableCell>
                      <TableCell className="text-slate-600">
{formatDateOnly(coe.fecha_liquidacion)}
                      </TableCell>
                      <TableCell>
                        <EstadoBadge estado={coe.estado} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => navigate(`/coes/${coe.id}`)}
                          >
                            Ver
                          </Button>
                          <span className="text-slate-300">|</span>
                          <button
                            type="button"
                            onClick={() => handleDownloadPdf(coe.id, coe.coe)}
                            disabled={downloadingPdfId === coe.id}
                            className="inline-flex items-center rounded-md bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700 ring-1 ring-inset ring-blue-200 hover:bg-blue-100 disabled:opacity-50"
                          >
                            {downloadingPdfId === coe.id ? "..." : "PDF"}
                          </button>
                        </div>
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
