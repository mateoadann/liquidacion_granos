import type { Client, ClientValidationResult } from "./clients";

interface ConfigValidationPanelProps {
  client: Client;
  result: ClientValidationResult | null;
  isValidating: boolean;
  errorMessage: string | null;
  onRevalidate: () => Promise<void> | void;
  onBack: () => void;
}

const CHECK_ITEMS = [
  { key: "empresa_cargada", label: "Empresa cargada" },
  { key: "cuit_valido", label: "CUIT válido" },
  { key: "cuit_representado_valido", label: "CUIT representado válido" },
  { key: "clave_fiscal_cargada", label: "Clave fiscal cargada" },
  { key: "certificados_cargados", label: "Certificados cargados" },
  { key: "certificados_validos", label: "Certificados válidos" },
] as const;

export default function ConfigValidationPanel({
  client,
  result,
  isValidating,
  errorMessage,
  onRevalidate,
  onBack,
}: ConfigValidationPanelProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-2xl font-semibold text-slate-900">Validación de configuración</h2>
      <p className="mt-1 text-sm text-slate-600">{client.empresa}</p>

      <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4">
        <p className="font-medium text-slate-800">Checklist de readiness</p>

        <ul className="mt-3 space-y-1 text-sm">
          {CHECK_ITEMS.map((item) => {
            const value = result?.checks[item.key];

            return (
              <li key={item.key} className={value ? "text-emerald-700" : "text-amber-700"}>
                {value ? "✓" : "⚠"} {item.label}
              </li>
            );
          })}
        </ul>

        <div
          className={`mt-4 rounded-md p-3 text-sm font-semibold ${
            result?.ready
              ? "bg-emerald-50 text-emerald-700"
              : "bg-red-50 text-red-700"
          }`}
        >
          {result?.statusText ?? "Configuración incompleta"}
        </div>
      </div>

      {errorMessage ? (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {errorMessage}
        </p>
      ) : null}

      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          disabled={isValidating}
          onClick={() => void onRevalidate()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Revalidar
        </button>
        <button
          type="button"
          onClick={onBack}
          disabled={isValidating}
          className="rounded-md bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-300 disabled:opacity-50"
        >
          Volver al listado
        </button>
      </div>
    </section>
  );
}
