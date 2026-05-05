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
  Input,
  Drawer,
  Combobox,
} from "../components/ui";
import { useCoesQuery } from "../hooks/useCoes";
import { useClientsQuery } from "../useClients";
import { downloadCoePdf, type Coe } from "../api/coes";

function EstadoCicloBadge({ estado }: { estado: string | null | undefined }) {
  const variants: Record<string, "success" | "warning" | "error" | "default"> = {
    pendiente: "warning",
    descargado: "default",
    cargado: "success",
    error: "error",
  };
  const labels: Record<string, string> = {
    pendiente: "Pendiente",
    descargado: "Descargado",
    cargado: "Cargado",
    error: "Error",
  };
  const key = estado ?? "";
  return (
    <Badge variant={variants[key] ?? "default"}>
      {labels[key] ?? "-"}
    </Badge>
  );
}

function getTipoCte(coe: Coe): "F1" | "F2" | "NL" | "-" {
  if (coe.tipo_documento === "AJUSTE") return "NL";
  if (coe.coe?.startsWith("3301")) return "F1";
  if (coe.coe?.startsWith("3302")) return "F2";
  return "-";
}


export function CoesListPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [taxpayerId, setTaxpayerId] = useState<number | undefined>();
  const [estadoCiclo, setEstadoCiclo] = useState<string>("");
  const [fechaDesde, setFechaDesde] = useState<string>("");
  const [fechaHasta, setFechaHasta] = useState<string>("");
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [downloadingPdfId, setDownloadingPdfId] = useState<number | null>(null);

  const clientsQuery = useClientsQuery();
  const coesQuery = useCoesQuery({
    page,
    per_page: 20,
    taxpayer_id: taxpayerId,
    estado_ciclo: estadoCiclo || undefined,
    fecha_desde: fechaDesde || undefined,
    fecha_hasta: fechaHasta || undefined,
    search: search || undefined,
  });

  const drawerFilterCount =
    (taxpayerId !== undefined ? 1 : 0) +
    (estadoCiclo ? 1 : 0) +
    (fechaDesde || fechaHasta ? 1 : 0);

  const hasActiveFilters = !!search || drawerFilterCount > 0;

  function handleClearFilters() {
    setSearch("");
    setTaxpayerId(undefined);
    setEstadoCiclo("");
    setFechaDesde("");
    setFechaHasta("");
    setPage(1);
  }

  function handleFechaDesdeChange(value: string) {
    setFechaDesde(value);
    if (fechaHasta && value && value > fechaHasta) {
      setFechaHasta("");
    }
    setPage(1);
  }

  function handleFechaHastaChange(value: string) {
    setFechaHasta(value);
    setPage(1);
  }

  const clients = clientsQuery.data ?? [];

  function handleSearch(value: string) {
    setSearch(value);
    setPage(1);
  }

  function handleTaxpayerChange(value: string) {
    setTaxpayerId(value ? Number(value) : undefined);
    setPage(1);
  }

  function handleEstadoCicloChange(value: string) {
    setEstadoCiclo(value);
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
        <div className="p-4 border-b border-slate-200">
          <div className="flex flex-col md:flex-row gap-3 md:items-center">
            <div className="flex-1">
              <SearchInput
                value={search}
                onChange={handleSearch}
                placeholder="Buscar por COE..."
              />
            </div>
            <Button
              variant="secondary"
              onClick={() => setIsFilterOpen(true)}
              className="md:w-auto"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
                />
              </svg>
              Filtros
              {drawerFilterCount > 0 ? (
                <span className="ml-1 inline-flex items-center justify-center rounded-full bg-green-600 text-white text-xs font-semibold w-5 h-5">
                  {drawerFilterCount}
                </span>
              ) : null}
            </Button>
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
                  <TableCell header>Tipo Cte</TableCell>
                  <TableCell header>Cliente</TableCell>
                  <TableCell header>Fecha</TableCell>
                  <TableCell header>Estado Ciclo</TableCell>
                  <TableCell header className="w-20"></TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coesQuery.data?.coes.map((coe) => {
                  const client = clients.find((c) => c.id === coe.taxpayer_id);
                  return (
                    <TableRow key={coe.id}>
                      <TableCell className="font-mono">
                        {coe.coe ? (
                          <button
                            type="button"
                            onClick={() => navigate(`/coes/${coe.id}`)}
                            className="text-green-700 hover:text-green-800 hover:underline focus:outline-none focus:underline"
                          >
                            {coe.coe}
                          </button>
                        ) : (
                          "-"
                        )}
                      </TableCell>
                      <TableCell>
                        {coe.tipo_documento === "AJUSTE" ? (
                          <Badge variant="warning">Ajuste</Badge>
                        ) : (
                          <Badge variant="default">Liquidacion</Badge>
                        )}
                      </TableCell>
                      <TableCell className="font-mono">{getTipoCte(coe)}</TableCell>
                      <TableCell>{client?.empresa ?? `ID: ${coe.taxpayer_id}`}</TableCell>
                      <TableCell className="text-slate-600">
                        {formatDateOnly(coe.fecha_liquidacion)}
                      </TableCell>
                      <TableCell>
                        <EstadoCicloBadge estado={coe.coe_estado?.estado} />
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

      <Drawer
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        title="Filtros"
        footer={
          <>
            <Button
              variant="ghost"
              onClick={handleClearFilters}
              disabled={!hasActiveFilters}
            >
              Limpiar filtros
            </Button>
            <Button variant="primary" onClick={() => setIsFilterOpen(false)}>
              Cerrar
            </Button>
          </>
        }
      >
        <div className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Cliente
            </label>
            <Combobox
              value={taxpayerId?.toString() ?? ""}
              onChange={handleTaxpayerChange}
              options={clients.map((c) => ({
                value: c.id.toString(),
                label: c.empresa,
              }))}
              placeholder="Todos los clientes"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Estado Ciclo
            </label>
            <Select
              value={estadoCiclo}
              onChange={(e) => handleEstadoCicloChange(e.target.value)}
              options={[
                { value: "", label: "Todos los estados" },
                { value: "pendiente", label: "Pendiente" },
                { value: "descargado", label: "Descargado" },
                { value: "cargado", label: "Cargado" },
                { value: "error", label: "Error" },
              ]}
            />
          </div>

          <div>
            <p className="block text-sm font-medium text-slate-700 mb-1.5">
              Fecha de emisión
            </p>
            <div className="space-y-3">
              <Input
                type="date"
                label="Desde"
                value={fechaDesde}
                max={fechaHasta || undefined}
                onChange={(e) => handleFechaDesdeChange(e.target.value)}
              />
              <Input
                type="date"
                label="Hasta"
                value={fechaHasta}
                min={fechaDesde || undefined}
                onChange={(e) => handleFechaHastaChange(e.target.value)}
              />
            </div>
          </div>
        </div>
      </Drawer>
    </div>
  );
}
