import { useState, type FormEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, Button, Alert, Spinner, Modal, ConfirmModal } from "../components/ui";
import { useClientQuery } from "../hooks/useClient";
import {
  useUploadCertificatesMutation,
  useTestCertificatesMutation,
  useRemoveCertificatesMutation,
} from "../useClients";
import { formatDateTime } from "../dateUtils";
import { generateClientCsr, type CertTestResult } from "../clients";

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
  const [showUploadModal, setShowUploadModal] = useState(false);

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

  const hasExistingKey = Boolean(client.keyFileName);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!certFile) {
      setLocalError("Debe seleccionar el archivo .crt.");
      return;
    }
    if (!hasExistingKey && !keyFile) {
      setLocalError("Debe seleccionar ambos archivos: .crt y .key.");
      return;
    }

    setLocalError(null);
    setSuccessMessage(null);

    try {
      const response = await uploadMutation.mutateAsync({
        clientId,
        certFile,
        keyFile: hasExistingKey ? null : keyFile,
      });
      setSuccessMessage(response.message ?? "Certificados cargados correctamente");
      setCertFile(null);
      setKeyFile(null);
      setShowUploadModal(false);
      clientQuery.refetch();
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
          <div className="flex gap-2">
            <Button onClick={() => setShowUploadModal(true)}>
              Subir certificados
            </Button>
            <Button variant="secondary" onClick={() => navigate(`/clientes/${client.id}`)}>
              Volver al cliente
            </Button>
          </div>
        }
      />

      {successMessage && <Alert variant="success" className="mb-6">{successMessage}</Alert>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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

        <TestCertificatesSection clientId={clientId} hasCertificates={client.certificadosCargados} />
      </div>

      {!client.certificadosCargados && (
        <div className="mt-6">
          {hasExistingKey ? (
            <ResetCertificatesSection
              clientId={clientId}
              keyFileName={client.keyFileName}
              onReset={() => clientQuery.refetch()}
            />
          ) : (
            <GenerateCsrSection clientId={clientId} onGenerated={() => clientQuery.refetch()} />
          )}
        </div>
      )}

      <CertificateTutorial />

      <Modal
        isOpen={showUploadModal}
        onClose={() => { setShowUploadModal(false); setLocalError(null); }}
        title="Subir certificados"
        size="md"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          {hasExistingKey ? (
            <Alert variant="info">
              Ya hay una clave privada cargada en el servidor (<span className="font-mono">{client.keyFileName}</span>).
              Solo necesitas subir el archivo <strong>.crt</strong> obtenido desde ARCA.
            </Alert>
          ) : null}

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

          {hasExistingKey ? null : (
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
          )}

          {error ? <Alert variant="error">{error}</Alert> : null}

          <div className="flex justify-end gap-2 pt-4 border-t border-slate-200">
            <Button variant="secondary" onClick={() => { setShowUploadModal(false); setLocalError(null); }}>
              Cancelar
            </Button>
            <Button type="submit" isLoading={uploadMutation.isPending}>
              Subir certificados
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function GenerateCsrSection({ clientId, onGenerated }: { clientId: number; onGenerated: () => void }) {
  const [certName, setCertName] = useState("");
  const [loading, setLoading] = useState(false);
  const [csrError, setCsrError] = useState<string | null>(null);
  const [csrSuccess, setCsrSuccess] = useState<string | null>(null);

  async function handleGenerate(e: FormEvent) {
    e.preventDefault();
    if (!certName.trim()) {
      setCsrError("Ingrese un nombre para el certificado");
      return;
    }
    setCsrError(null);
    setCsrSuccess(null);
    setLoading(true);
    try {
      const blob = await generateClientCsr(clientId, certName.trim());
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${certName.trim()}.csr`;
      a.click();
      URL.revokeObjectURL(url);
      setCsrSuccess(`Archivos generados. El .key se guardo en el servidor. Suba el archivo ${certName.trim()}.csr a ARCA para obtener el .crt`);
      onGenerated();
    } catch (err) {
      setCsrError(err instanceof Error ? err.message : "Error al generar CSR");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <h3 className="text-lg font-medium text-slate-900 mb-2">Generar clave privada y CSR</h3>
      <p className="text-sm text-slate-500 mb-4">
        Genera el archivo .key (se guarda en el servidor) y descarga el .csr para subir a ARCA.
      </p>
      <form onSubmit={handleGenerate} className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Nombre del certificado (CN)
          </label>
          <input
            type="text"
            value={certName}
            onChange={(e) => setCertName(e.target.value.replace(/[^a-zA-Z0-9_]/g, ""))}
            placeholder="ej: mi_certificado"
            className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-green-500 focus:ring-green-500"
          />
          <p className="text-xs text-slate-400 mt-1">Solo letras, numeros y guion bajo.</p>
        </div>

        {csrError && <Alert variant="error">{csrError}</Alert>}
        {csrSuccess && <Alert variant="success">{csrSuccess}</Alert>}

        <div className="flex justify-end pt-2 border-t border-slate-200">
          <Button type="submit" isLoading={loading}>
            Generar key + CSR
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ResetCertificatesSection({
  clientId,
  keyFileName,
  onReset,
}: {
  clientId: number;
  keyFileName: string | null;
  onReset: () => void;
}) {
  const removeMutation = useRemoveCertificatesMutation();
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  async function handleConfirm() {
    try {
      await removeMutation.mutateAsync(clientId);
      setIsConfirmOpen(false);
      onReset();
    } catch {
      // El error queda visible vía errorMessage del modal
    }
  }

  function handleClose() {
    if (removeMutation.isPending) return;
    setIsConfirmOpen(false);
    removeMutation.reset();
  }

  return (
    <Card>
      <h3 className="text-lg font-medium text-slate-900 mb-2">Clave privada generada</h3>
      <p className="text-sm text-slate-500 mb-4">
        Ya hay una clave privada (<span className="font-mono">{keyFileName ?? "private.key"}</span>) generada en el servidor.
        Subí el <strong>.crt</strong> que descargaste de ARCA con el botón <strong>Subir certificados</strong> de arriba.
        Si necesitás empezar de cero, eliminá la clave actual.
      </p>
      <div className="flex justify-end pt-2 border-t border-slate-200">
        <Button variant="danger" onClick={() => setIsConfirmOpen(true)}>
          Resetear y regenerar
        </Button>
      </div>

      <ConfirmModal
        isOpen={isConfirmOpen}
        onClose={handleClose}
        onConfirm={handleConfirm}
        title="Resetear clave privada"
        message="Se eliminará la clave privada actual del servidor. Vas a tener que generar una nueva clave + CSR y volver a hacer todo el proceso en ARCA."
        confirmLabel="Resetear"
        variant="danger"
        isLoading={removeMutation.isPending}
      />
    </Card>
  );
}

function TutorialImg({ src, alt }: { src: string; alt: string }) {
  return (
    <img
      src={src}
      alt={alt}
      className="rounded border border-slate-200 mt-2 max-w-full"
      loading="lazy"
    />
  );
}

function TutorialStep({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-green-600 text-white text-sm font-bold flex items-center justify-center">
        {number}
      </div>
      <div className="flex-1 min-w-0">
        <h5 className="text-sm font-medium text-slate-900 mb-1">{title}</h5>
        <div className="text-sm text-slate-600 space-y-2">{children}</div>
      </div>
    </div>
  );
}

function TutorialSection({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-slate-200 rounded">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
      >
        <span className="text-sm font-medium text-slate-800">{title}</span>
        <span className="text-slate-400 text-xs">{open ? "Colapsar" : "Expandir"}</span>
      </button>
      {open && <div className="px-4 pb-4 space-y-4">{children}</div>}
    </div>
  );
}

function CertificateTutorial() {
  const [expanded, setExpanded] = useState(false);
  const T = "/tutorial";

  return (
    <Card className="mt-6">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div>
          <h3 className="text-lg font-medium text-slate-900 text-left">Tutorial: Configurar certificados de ARCA</h3>
          <p className="text-sm text-slate-500 text-left mt-1">
            Guia paso a paso para habilitar, generar y autorizar certificados digitales en ARCA/AFIP.
          </p>
        </div>
        <span className="text-sm text-green-600 font-medium flex-shrink-0 ml-4">
          {expanded ? "Ocultar" : "Ver tutorial"}
        </span>
      </button>

      {expanded && (
        <div className="mt-4 space-y-4">
          <TutorialSection title="Paso 1: Habilitar Administrador de Certificados Digitales">
            <TutorialStep number={1} title="Ingresar al Administrador de Relaciones de Clave Fiscal">
              <p>
                Desde el escritorio de ARCA, buscar y acceder al servicio{" "}
                <strong>Administrador de Relaciones de Clave Fiscal</strong>.
              </p>
              <TutorialImg src={`${T}/paso1-01-admin-relaciones.png`} alt="Administrador de Relaciones de Clave Fiscal" />
            </TutorialStep>
            <TutorialStep number={2} title="Seleccionar el contribuyente">
              <p>
                Si se administran relaciones de otros contribuyentes, seleccionar el contribuyente deseado.
                De lo contrario, se selecciona automaticamente la cuenta propia.
              </p>
              <TutorialImg src={`${T}/paso1-02-seleccionar-contribuyente.png`} alt="Seleccionar contribuyente" />
            </TutorialStep>
            <TutorialStep number={3} title='Elegir "Adherir servicio"'>
              <p>Hacer clic en la opcion <strong>Adherir servicio</strong>.</p>
              <TutorialImg src={`${T}/paso1-03-adherir-servicio.png`} alt="Adherir servicio" />
            </TutorialStep>
            <TutorialStep number={4} title="Seleccionar el servicio de certificados">
              <p>
                Navegar a:{" "}
                <strong>ARCA &gt; Servicios interactivos &gt; Administracion de Certificados Digitales</strong>.
              </p>
              <TutorialImg src={`${T}/paso1-04-cert-digitales.png`} alt="Administracion de Certificados Digitales" />
            </TutorialStep>
            <TutorialStep number={5} title="Confirmar">
              <p>
                Hacer clic en <strong>Confirmar</strong>. El servicio quedara disponible en el escritorio de ARCA.
              </p>
              <TutorialImg src={`${T}/paso1-05-confirmar.png`} alt="Confirmar servicio" />
            </TutorialStep>
          </TutorialSection>

          <TutorialSection title="Paso 2: Generar el certificado digital">
            <TutorialStep number={1} title="Generar la clave privada (key)">
              <p>Ejecutar en una terminal:</p>
              <code className="block bg-slate-100 rounded px-3 py-2 text-xs font-mono text-slate-800 overflow-x-auto">
                openssl genrsa -traditional -out certificado.key 2048
              </code>
              <p className="text-xs text-slate-400">
                En versiones antiguas de OpenSSL, quitar el parametro <code>-traditional</code>.
              </p>
            </TutorialStep>
            <TutorialStep number={2} title="Generar el CSR (solicitud de certificado)">
              <p>Ejecutar reemplazando los datos del contribuyente:</p>
              <code className="block bg-slate-100 rounded px-3 py-2 text-xs font-mono text-slate-800 overflow-x-auto whitespace-pre-wrap">
                {"openssl req -new -key certificado.key -subj \"/C=AR/O=NOMBRE_EMPRESA/CN=nombre_certificado/serialNumber=CUIT XXXXXXXXXXX\" -out certificado.csr"}
              </code>
              <p className="text-xs text-slate-400">
                <strong>CN</strong>: nombre identificador del certificado (solo alfanumerico).{" "}
                <strong>serialNumber</strong>: CUIT del contribuyente representado con formato &quot;CUIT XXXXXXXXXXX&quot;.
              </p>
            </TutorialStep>
            <TutorialStep number={3} title="Subir el CSR a ARCA">
              <p>
                Acceder a <strong>Administracion de Certificados Digitales</strong> desde el escritorio de ARCA.
              </p>
              <TutorialImg src={`${T}/paso2-01-admin-cert.png`} alt="Administracion de Certificados Digitales" />
              <ol className="list-decimal list-inside space-y-1 text-sm mt-2">
                <li>Seleccionar <strong>Agregar alias</strong></li>
                <li>Ingresar el nombre del certificado (mismo que el CN del CSR)</li>
                <li>Subir el archivo <strong>.csr</strong> generado</li>
                <li>Hacer clic en <strong>Agregar Alias</strong></li>
              </ol>
              <TutorialImg src={`${T}/paso2-02-agregar-alias.png`} alt="Agregar alias" />
              <TutorialImg src={`${T}/paso2-03-subir-csr.png`} alt="Subir CSR" />
            </TutorialStep>
            <TutorialStep number={4} title="Descargar el certificado (.crt)">
              <p>
                En la lista de alias, buscar el certificado recien creado, hacer clic en <strong>Ver</strong>{" "}
                y descargar el archivo <strong>.crt</strong>.
              </p>
              <TutorialImg src={`${T}/paso2-04-descargar-crt.png`} alt="Descargar certificado" />
              <p className="text-xs text-slate-400 mt-2">
                El archivo .csr ya no es necesario. Los archivos importantes son el <strong>.crt</strong> (certificado) y el <strong>.key</strong> (clave privada).
              </p>
            </TutorialStep>
          </TutorialSection>

          <TutorialSection title="Paso 3: Autorizar los Web Services de produccion">
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-800">
              <strong>Importante:</strong> Este paso debe realizarse <strong>dos veces</strong>, una por cada web service requerido:
              <ul className="list-disc list-inside mt-1 space-y-0.5">
                <li><strong>ws_sr_constancia_inscripcion</strong> — Consulta de Constancia de Inscripcion (Padron)</li>
                <li><strong>wslpg</strong> — Liquidacion Primaria de Granos</li>
              </ul>
            </div>
            <TutorialStep number={1} title="Acceder al Administrador de Relaciones">
              <p>Desde el escritorio de ARCA, abrir <strong>Administrador de Relaciones de Clave Fiscal</strong>.</p>
              <TutorialImg src={`${T}/paso1-01-admin-relaciones.png`} alt="Administrador de Relaciones" />
            </TutorialStep>
            <TutorialStep number={2} title="Seleccionar contribuyente">
              <p>Si corresponde, elegir el contribuyente para el cual se va a autorizar el servicio.</p>
              <TutorialImg src={`${T}/paso1-02-seleccionar-contribuyente.png`} alt="Seleccionar contribuyente" />
            </TutorialStep>
            <TutorialStep number={3} title='Crear "Nueva Relacion"'>
              <p>Hacer clic en <strong>Nueva Relacion</strong>.</p>
              <TutorialImg src={`${T}/paso3-01-nueva-relacion.png`} alt="Nueva Relacion" />
            </TutorialStep>
            <TutorialStep number={4} title="Configurar representado">
              <p>
                En el campo <strong>Representado</strong>, seleccionar el CUIT del contribuyente que delega
                el acceso (si aplica). Luego hacer clic en <strong>Buscar</strong>.
              </p>
              <TutorialImg src={`${T}/paso3-02-representado.png`} alt="Configurar representado" />
            </TutorialStep>
            <TutorialStep number={5} title="Seleccionar el Web Service">
              <p>
                Navegar a <strong>ARCA &gt; Web Services</strong> y elegir el servicio a autorizar:
              </p>
              <ul className="list-disc list-inside space-y-0.5">
                <li><strong>ws_sr_constancia_inscripcion</strong> para consultas de padron</li>
                <li><strong>wslpg</strong> para liquidacion primaria de granos</li>
              </ul>
              <TutorialImg src={`${T}/paso3-03-web-services.png`} alt="Seleccionar Web Service" />
            </TutorialStep>
            <TutorialStep number={6} title="Asociar el certificado">
              <p>
                Hacer clic en <strong>Buscar</strong> para ver los certificados disponibles.
                Seleccionar el certificado creado en el paso anterior y hacer clic en <strong>Confirmar</strong>.
              </p>
              <TutorialImg src={`${T}/paso3-04-seleccionar-cert.png`} alt="Seleccionar certificado" />
              <TutorialImg src={`${T}/paso3-05-confirmar-cert.png`} alt="Confirmar certificado" />
            </TutorialStep>
            <TutorialStep number={7} title="Confirmar la autorizacion">
              <p>
                Hacer clic en <strong>Confirmar</strong> nuevamente para completar la autorizacion.
              </p>
              <TutorialImg src={`${T}/paso3-06-confirmar-final.png`} alt="Confirmar autorizacion" />
              <p className="text-xs text-slate-400 mt-2">
                Repetir desde el paso 3 para autorizar el segundo web service.
              </p>
            </TutorialStep>
          </TutorialSection>

          <div className="bg-green-50 border border-green-200 rounded p-3 text-sm text-green-800">
            Una vez completados los 3 pasos, suba los archivos <strong>.crt</strong> y <strong>.key</strong>{" "}
            en el formulario de arriba y luego use <strong>Probar certificados</strong> para verificar que
            ambos web services estan correctamente autorizados.
          </div>
        </div>
      )}
    </Card>
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
