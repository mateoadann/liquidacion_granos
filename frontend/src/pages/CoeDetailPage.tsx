import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, CardHeader, Badge, Button, Spinner, Alert } from "../components/ui";
import { useCoeQuery } from "../hooks/useCoes";

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

export function CoeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const coeId = Number(id);

  const coeQuery = useCoeQuery(coeId);
  const coe = coeQuery.data;

  if (coeQuery.isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (coeQuery.isError || !coe) {
    return (
      <div>
        <PageHeader title="Error" />
        <Alert variant="error">COE no encontrado</Alert>
        <Button variant="secondary" onClick={() => navigate("/coes")} className="mt-4">
          Volver a COEs
        </Button>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={`COE: ${coe.coe ?? "Sin número"}`}
        subtitle={coe.taxpayer?.empresa}
        actions={
          <Button variant="secondary" onClick={() => navigate("/coes")}>
            Volver
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Información del Documento" />
          <dl className="space-y-4">
            <div>
              <dt className="text-sm font-medium text-slate-500">COE</dt>
              <dd className="mt-1 font-mono text-slate-900">{coe.coe ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Estado</dt>
              <dd className="mt-1">
                <EstadoBadge estado={coe.estado} />
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Tipo Documento</dt>
              <dd className="mt-1 text-slate-900">{coe.tipo_documento}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Punto Emisión</dt>
              <dd className="mt-1 text-slate-900">{coe.pto_emision ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Número Orden</dt>
              <dd className="mt-1 text-slate-900">{coe.nro_orden ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Fecha Creación</dt>
              <dd className="mt-1 text-slate-900">
                {coe.created_at
                  ? new Date(coe.created_at).toLocaleString("es-AR")
                  : "-"}
              </dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHeader title="Cliente" />
          {coe.taxpayer ? (
            <dl className="space-y-4">
              <div>
                <dt className="text-sm font-medium text-slate-500">Empresa</dt>
                <dd className="mt-1 text-slate-900">{coe.taxpayer.empresa}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-slate-500">CUIT</dt>
                <dd className="mt-1 font-mono text-slate-900">{coe.taxpayer.cuit}</dd>
              </div>
              <div className="pt-4 border-t border-slate-200">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/clientes/${coe.taxpayer!.id}`)}
                >
                  Ver cliente
                </Button>
              </div>
            </dl>
          ) : (
            <p className="text-slate-500">Cliente no disponible</p>
          )}
        </Card>

        {coe.raw_data ? (
          <Card className="lg:col-span-2">
            <CardHeader title="Datos Crudos" />
            <pre className="bg-slate-50 p-4 rounded-lg text-xs overflow-x-auto">
              {JSON.stringify(coe.raw_data, null, 2)}
            </pre>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
