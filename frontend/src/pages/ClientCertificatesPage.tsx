import { useState, type FormEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, Button, Alert, Spinner } from "../components/ui";
import { useClientQuery } from "../hooks/useClient";
import { useUploadCertificatesMutation, useTestCertificatesMutation } from "../useClients";
import { formatDateTime } from "../dateUtils";
import type { CertTestResult } from "../clients";

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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Columna izquierda */}
        <div className="space-y-6">
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

        {/* Columna derecha */}
        <div>
          <TestCertificatesSection clientId={clientId} hasCertificates={client.certificadosCargados} />
        </div>
      </div>
    </div>
  );
}

function StatusIcon({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="text-green-600 font-bold">OK</span>
  ) : (
    <span className="text-red-600 font-bold">ERROR</span>
  );
}

const CHECK_LABELS: Record<string, string> = {
  has_empresa: "Empresa configurada",
  has_cuit: "CUIT valido",
  has_cuit_representado: "CUIT representado valido",
  has_clave_fiscal: "Clave fiscal cargada",
  has_certificates: "Certificados cargados",
  certificates_valid: "Certificados validos (par criptografico)",
};

function TestCertificatesSection({ clientId, hasCertificates }: { clientId: number; hasCertificates: boolean }) {
  const testMutation = useTestCertificatesMutation();
  const [result, setResult] = useState<CertTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  async function handleTest() {
    setResult(null);
    setTestError(null);
    try {
      const data = await testMutation.mutateAsync(clientId);
      setResult(data);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : "Error al probar certificados");
    }
  }

  return (
    <Card>
      <h3 className="text-lg font-medium text-slate-900 mb-4">Probar conexion con ARCA</h3>
      <p className="text-sm text-slate-500 mb-4">
        Verifica la configuracion local y prueba la conexion real contra los web services de ARCA (WSLPG y Padron).
      </p>

      <Button
        onClick={handleTest}
        isLoading={testMutation.isPending}
        disabled={!hasCertificates}
      >
        {testMutation.isPending ? "Probando..." : "Probar certificados"}
      </Button>

      {!hasCertificates && (
        <p className="text-xs text-slate-400 mt-2">Suba certificados primero para poder probar.</p>
      )}

      {testError && <Alert variant="error" className="mt-4">{testError}</Alert>}

      {result && (
        <div className="mt-4 space-y-4">
          {/* Configuracion local */}
          <div className="border border-slate-200 rounded p-3">
            <h4 className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-2">
              Configuracion local <StatusIcon ok={result.config.ok} />
            </h4>
            <dl className="space-y-1">
              {Object.entries(result.config.checks).map(([key, ok]) => (
                <div key={key} className="flex justify-between text-xs py-0.5">
                  <dt className="text-slate-500">{CHECK_LABELS[key] ?? key}</dt>
                  <dd>{ok ? <span className="text-green-600">OK</span> : <span className="text-red-500">Falta</span>}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* WSLPG */}
          <div className="border border-slate-200 rounded p-3">
            <h4 className="text-sm font-medium text-slate-700 mb-1 flex items-center gap-2">
              Web Service LPG (wslpg) <StatusIcon ok={result.wslpg.ok} />
            </h4>
            <p className={`text-xs ${result.wslpg.ok ? "text-green-600" : "text-red-500"}`}>
              {result.wslpg.message}
            </p>
          </div>

          {/* Constancia / Padron */}
          <div className="border border-slate-200 rounded p-3">
            <h4 className="text-sm font-medium text-slate-700 mb-1 flex items-center gap-2">
              Web Service Padron (ws_sr_constancia_inscripcion) <StatusIcon ok={result.constancia.ok} />
            </h4>
            <p className={`text-xs ${result.constancia.ok ? "text-green-600" : "text-red-500"}`}>
              {result.constancia.message}
              {result.constancia.razonSocial ? ` — ${result.constancia.razonSocial}` : ""}
            </p>
          </div>

          {/* Info del certificado */}
          {result.certificate_info && (
            <div className="border border-slate-200 rounded p-3">
              <h4 className="text-sm font-medium text-slate-700 mb-2">Informacion del certificado</h4>
              <dl className="space-y-1 text-xs">
                <div className="flex justify-between py-0.5">
                  <dt className="text-slate-500">Subject</dt>
                  <dd className="text-slate-900 font-mono text-right max-w-xs truncate">{result.certificate_info.subject}</dd>
                </div>
                <div className="flex justify-between py-0.5">
                  <dt className="text-slate-500">Emisor</dt>
                  <dd className="text-slate-900 font-mono text-right max-w-xs truncate">{result.certificate_info.issuer}</dd>
                </div>
                <div className="flex justify-between py-0.5">
                  <dt className="text-slate-500">Valido desde</dt>
                  <dd className="text-slate-900">{result.certificate_info.not_before}</dd>
                </div>
                <div className="flex justify-between py-0.5">
                  <dt className="text-slate-500">Valido hasta</dt>
                  <dd className={result.certificate_info.expired ? "text-red-600 font-bold" : "text-slate-900"}>
                    {result.certificate_info.not_after}
                    {result.certificate_info.expired ? " (VENCIDO)" : ""}
                  </dd>
                </div>
              </dl>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
