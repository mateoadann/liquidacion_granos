import { useEffect, useMemo, useState, type FormEvent } from "react";
import type { Client, ClientEnvironment } from "./clients";

export type ClientFormMode = "create" | "edit";

export interface ClientFormValues {
  empresa: string;
  cuit: string;
  cuitRepresentado: string;
  ambiente: ClientEnvironment;
  claveFiscal: string;
  activo: boolean;
}

interface ClientFormProps {
  mode: ClientFormMode;
  client: Client | null;
  isSubmitting: boolean;
  errorMessage: string | null;
  onSubmit: (values: ClientFormValues) => Promise<void> | void;
  onCancel: () => void;
}

const EMPTY_VALUES: ClientFormValues = {
  empresa: "",
  cuit: "",
  cuitRepresentado: "",
  ambiente: "homologacion",
  claveFiscal: "",
  activo: true,
};

function buildInitialValues(client: Client | null): ClientFormValues {
  if (!client) return EMPTY_VALUES;

  return {
    empresa: client.empresa,
    cuit: client.cuit,
    cuitRepresentado: client.cuitRepresentado,
    ambiente: client.ambiente,
    claveFiscal: "",
    activo: client.activo,
  };
}

function isValidCuit(value: string): boolean {
  return /^\d{11}$/.test(value.trim());
}

export default function ClientForm({
  mode,
  client,
  isSubmitting,
  errorMessage,
  onSubmit,
  onCancel,
}: ClientFormProps) {
  const [values, setValues] = useState<ClientFormValues>(() => buildInitialValues(client));
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  useEffect(() => {
    setValues(buildInitialValues(client));
    setValidationErrors([]);
  }, [client, mode]);

  const title = mode === "create" ? "Nuevo cliente" : "Editar cliente";

  const fieldErrors = useMemo(() => {
    const errors: string[] = [];

    if (!values.empresa.trim()) {
      errors.push("La empresa es obligatoria.");
    }

    if (!isValidCuit(values.cuit)) {
      errors.push("CUIT debe tener 11 dígitos.");
    }

    if (!isValidCuit(values.cuitRepresentado)) {
      errors.push("CUIT representado debe tener 11 dígitos.");
    }

    if (mode === "create" && !values.claveFiscal.trim()) {
      errors.push("La clave fiscal es obligatoria para el alta.");
    }

    return errors;
  }, [mode, values]);

  function setField<K extends keyof ClientFormValues>(key: K, value: ClientFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (fieldErrors.length > 0) {
      setValidationErrors(fieldErrors);
      return;
    }

    setValidationErrors([]);
    void onSubmit(values);
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-2xl font-semibold text-slate-900">{title}</h2>

      <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Empresa</span>
          <input
            value={values.empresa}
            onChange={(event) => setField("empresa", event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">CUIT (11 dígitos)</span>
          <input
            value={values.cuit}
            onChange={(event) => setField("cuit", event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">
            CUIT representado (11 dígitos)
          </span>
          <input
            value={values.cuitRepresentado}
            onChange={(event) => setField("cuitRepresentado", event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Ambiente</span>
          <select
            value={values.ambiente}
            onChange={(event) =>
              setField("ambiente", event.target.value as ClientEnvironment)
            }
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          >
            <option value="homologacion">homologacion</option>
            <option value="produccion">produccion</option>
          </select>
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Clave fiscal</span>
          <input
            type="password"
            value={values.claveFiscal}
            onChange={(event) => setField("claveFiscal", event.target.value)}
            placeholder={
              mode === "edit" ? "Dejar vacío para no modificar" : "Ingresar clave fiscal"
            }
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
          <p className="mt-1 text-xs text-slate-500">La clave fiscal se almacena cifrada</p>
        </label>

        {mode === "edit" ? (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={values.activo}
              onChange={(event) => setField("activo", event.target.checked)}
            />
            Activo (solo en edición)
          </label>
        ) : null}

        {validationErrors.length > 0 || errorMessage ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {validationErrors.length > 0 ? (
              <ul className="list-disc pl-4">
                {validationErrors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            ) : null}
            {errorMessage ? <p>{errorMessage}</p> : null}
          </div>
        ) : null}

        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Guardar
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="rounded-md bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-300 disabled:opacity-50"
          >
            Cancelar
          </button>
        </div>
      </form>
    </section>
  );
}
