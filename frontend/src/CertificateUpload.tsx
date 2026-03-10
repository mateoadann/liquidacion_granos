import { useState, type FormEvent } from "react";
import type { Client } from "./clients";
import { formatDateTime } from "./dateUtils";

interface CertificateUploadProps {
  client: Client;
  isSubmitting: boolean;
  successMessage: string | null;
  errorMessage: string | null;
  onUpload: (files: { certFile: File; keyFile: File }) => Promise<void> | void;
  onBack: () => void;
}

export default function CertificateUpload({
  client,
  isSubmitting,
  successMessage,
  errorMessage,
  onUpload,
  onBack,
}: CertificateUploadProps) {
  const [certFile, setCertFile] = useState<File | null>(null);
  const [keyFile, setKeyFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!certFile || !keyFile) {
      setLocalError("Debe seleccionar ambos archivos: cert_file y key_file.");
      return;
    }

    setLocalError(null);
    void onUpload({ certFile, keyFile });
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-2xl font-semibold text-slate-900">Certificados del cliente</h2>
      <p className="mt-1 text-sm text-slate-600">{client.empresa}</p>

      <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
        <p>Certificado actual: {client.certFileName ?? "No cargado"}</p>
        <p>Key actual: {client.keyFileName ?? "No cargado"}</p>
        <p>Fecha de carga: {formatDateTime(client.certUploadedAt)}</p>
      </div>

      <form onSubmit={submit} className="mt-4 space-y-4">
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">cert_file (.crt/.pem)</span>
          <input
            type="file"
            accept=".crt,.pem"
            onChange={(event) => setCertFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">key_file (.key)</span>
          <input
            type="file"
            accept=".key"
            onChange={(event) => setKeyFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm"
          />
        </label>

        {localError || errorMessage ?
          <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {localError ?? errorMessage}
          </p>
        : null}

        {successMessage ? (
          <p className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
            {successMessage}
          </p>
        ) : null}

        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Subir certificados
          </button>
          <button
            type="button"
            onClick={onBack}
            disabled={isSubmitting}
            className="rounded-md bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-300 disabled:opacity-50"
          >
            Volver
          </button>
        </div>
      </form>
    </section>
  );
}
