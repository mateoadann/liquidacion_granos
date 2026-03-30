import { useState, type FormEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, Button, Alert, Spinner } from "../components/ui";
import { useClientQuery } from "../hooks/useClient";
import { useUploadCertificatesMutation } from "../useClients";
import { formatDateTime } from "../dateUtils";

export function ClientCertificatesPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const clientId = Number(id);

  const clientQuery = useClientQuery(clientId);
  const uploadMutation = useUploadCertificatesMutation();

  const [certFile, setCertFile] = useState<File | null>(null);
  const [keyFile, setKeyFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!certFile || !keyFile) {
      setLocalError("Debe seleccionar ambos archivos: cert_file y key_file.");
      return;
    }

    setLocalError(null);
    setSuccessMessage(null);

    try {
      const response = await uploadMutation.mutateAsync({
        clientId,
        certFile,
        keyFile,
      });
      setSuccessMessage(response.message ?? "Certificados cargados correctamente");
      setCertFile(null);
      setKeyFile(null);
      // Reset file inputs
      const form = event.target as HTMLFormElement;
      form.reset();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Error al subir certificados");
    }
  }

  const error = localError || (uploadMutation.isError ? "Error al subir certificados" : null);

  return (
    <div>
      <PageHeader
        title="Certificados"
        subtitle={client.empresa}
        actions={
          <Button variant="secondary" onClick={() => navigate(`/clientes/${client.id}`)}>
            Volver al cliente
          </Button>
        }
      />

      <div className="max-w-2xl space-y-6">
        <Card>
          <h3 className="text-lg font-medium text-slate-900 mb-4">Estado actual</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between py-2 border-b border-slate-100">
              <dt className="text-slate-500">Certificado</dt>
              <dd className="text-slate-900 font-mono">{client.certFileName ?? "No cargado"}</dd>
            </div>
            <div className="flex justify-between py-2 border-b border-slate-100">
              <dt className="text-slate-500">Key</dt>
              <dd className="text-slate-900 font-mono">{client.keyFileName ?? "No cargado"}</dd>
            </div>
            <div className="flex justify-between py-2">
              <dt className="text-slate-500">Fecha de carga</dt>
              <dd className="text-slate-900">{formatDateTime(client.certUploadedAt)}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <h3 className="text-lg font-medium text-slate-900 mb-4">Subir nuevos certificados</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Certificado (.crt / .pem)
              </label>
              <input
                type="file"
                accept=".crt,.pem"
                onChange={(e) => setCertFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Key (.key)
              </label>
              <input
                type="file"
                accept=".key"
                onChange={(e) => setKeyFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
              />
            </div>

            {error ? <Alert variant="error">{error}</Alert> : null}
            {successMessage ? <Alert variant="success">{successMessage}</Alert> : null}

            <div className="flex justify-end pt-4 border-t border-slate-200">
              <Button type="submit" isLoading={uploadMutation.isPending}>
                Subir certificados
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}
