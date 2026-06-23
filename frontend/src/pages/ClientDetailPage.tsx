import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { formatDateOnly } from "../dateUtils";
import { PageHeader } from "../components/layout";
import { Card, CardHeader, Badge, Button, Spinner, Alert } from "../components/ui";
import { useClientQuery } from "../hooks/useClient";
import { fetchClaveFiscal } from "../clients";

function ClipboardIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
      />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M5 13l4 4L19 7"
      />
    </svg>
  );
}

export function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const clientId = Number(id);

  const [copyStatus, setCopyStatus] = useState<"idle" | "copying" | "copied" | "error">("idle");
  const [copyError, setCopyError] = useState<string | null>(null);

  const clientQuery = useClientQuery(clientId);
  const client = clientQuery.data;

  async function handleCopyKey() {
    setCopyStatus("copying");
    setCopyError(null);
    try {
      const value = await fetchClaveFiscal(clientId);
      await navigator.clipboard.writeText(value);
      // value is intentionally not stored in state — drop it immediately
      setCopyStatus("copied");
      setTimeout(() => setCopyStatus("idle"), 3000);
    } catch (err) {
      setCopyStatus("error");
      setCopyError(err instanceof Error ? err.message : "Error al copiar la clave fiscal.");
    }
  }

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
            <Button variant="secondary" onClick={() => navigate(-1)}>
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
              <dt className="text-sm font-medium text-slate-500">Extracción Automática</dt>
              <dd className="mt-1">
                <Badge variant={client.playwrightEnabled ? "success" : "default"}>
                  {client.playwrightEnabled ? "Habilitada" : "Deshabilitada"}
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
                <div className="flex items-center gap-2">
                  <Badge variant={client.claveFiscalCargada ? "success" : "warning"}>
                    {client.claveFiscalCargada ? "Cargada" : "Sin cargar"}
                  </Badge>
                  <button
                    type="button"
                    disabled={!client.claveFiscalCargada || copyStatus === "copying"}
                    title={
                      client.claveFiscalCargada
                        ? "Copiar clave al portapapeles"
                        : "Sin clave cargada"
                    }
                    aria-label="Copiar clave fiscal al portapapeles"
                    onClick={handleCopyKey}
                    className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-slate-400"
                  >
                    {copyStatus === "copied" ? (
                      <CheckIcon className="w-4 h-4 text-green-600" />
                    ) : (
                      <ClipboardIcon className="w-4 h-4" />
                    )}
                  </button>
                </div>
                {copyStatus === "error" && copyError && (
                  <p className="text-xs text-red-600 mt-1">{copyError}</p>
                )}
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
                        Subido: {formatDateOnly(client.certUploadedAt)}
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
