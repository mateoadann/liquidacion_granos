import { PageHeader } from "../components/layout";
import {
  Card,
  Spinner,
  Alert,
  Badge,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
} from "../components/ui";
import { useExtractionHealthQuery } from "../hooks/useExtractionHealth";
import type { ExtractionHealthEstado } from "../api/extracciones";

const ESTADO_LABEL: Record<ExtractionHealthEstado, string> = {
  verde: "OK",
  amarillo: "Atención",
  rojo: "Acción requerida",
  gris: "Sin datos",
};

const ESTADO_BADGE: Record<
  ExtractionHealthEstado,
  "success" | "warning" | "error" | "default"
> = {
  verde: "success",
  amarillo: "warning",
  rojo: "error",
  gris: "default",
};

const ESTADO_CARD: Record<ExtractionHealthEstado, string> = {
  verde: "border-emerald-200 bg-emerald-50 text-emerald-700",
  amarillo: "border-amber-200 bg-amber-50 text-amber-700",
  rojo: "border-red-200 bg-red-50 text-red-700",
  gris: "border-slate-200 bg-slate-50 text-slate-600",
};

const RESUMEN_ORDER: ExtractionHealthEstado[] = [
  "rojo",
  "amarillo",
  "gris",
  "verde",
];

export function ExtractionHealthPage() {
  const { data, isLoading, error } = useExtractionHealthQuery();

  return (
    <div>
      <PageHeader
        title="Salud de extracciones"
        subtitle="Estado de las extracciones diarias por empresa. Las filas en rojo requieren tu acción."
      />

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : error ? (
        <Alert variant="error">{error.message}</Alert>
      ) : !data ? null : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {RESUMEN_ORDER.map((estado) => (
              <div
                key={estado}
                className={`rounded-lg border p-4 ${ESTADO_CARD[estado]}`}
              >
                <div className="text-sm font-medium">
                  {ESTADO_LABEL[estado]}
                </div>
                <div className="text-3xl font-bold">
                  {data.resumen[estado]}
                </div>
              </div>
            ))}
          </div>

          <Card padding="none">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableCell header>Estado</TableCell>
                  <TableCell header>Empresa</TableCell>
                  <TableCell header className="whitespace-nowrap">Días sin éxito</TableCell>
                  <TableCell header>Causa</TableCell>
                  <TableCell header className="whitespace-nowrap">Última extracción OK</TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.clientes.map((c) => (
                  <TableRow key={c.taxpayer_id}>
                    <TableCell>
                      <Badge
                        variant={ESTADO_BADGE[c.estado]}
                        className="whitespace-nowrap"
                      >
                        {ESTADO_LABEL[c.estado]}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {c.empresa ?? "—"}
                    </TableCell>
                    <TableCell>
                      {c.dias_sin_exito === null ? "Nunca" : c.dias_sin_exito}
                    </TableCell>
                    <TableCell className="max-w-md">
                      {c.estado === "verde"
                        ? "—"
                        : c.causa_mensaje ?? "Causa desconocida"}
                    </TableCell>
                    <TableCell>{c.ultima_ok ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}
    </div>
  );
}
