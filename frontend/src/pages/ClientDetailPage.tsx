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
                {client.certificadosCargados ? (
                  <div className="space-y-1">
                    <Badge variant="success">Certificados válidos</Badge>
                    {client.certUploadedAt ? (
                      <p className="text-xs text-slate-500">
                        Subido: {new Date(client.certUploadedAt).toLocaleDateString("es-AR")}
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
