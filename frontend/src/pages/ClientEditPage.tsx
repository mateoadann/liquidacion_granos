import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, Button, Input, Select, Alert, Spinner } from "../components/ui";
import { useClientQuery } from "../hooks/useClient";
import { useUpdateClientMutation, useCreateClientMutation } from "../useClients";
import { useState, useEffect } from "react";

interface FormData {
  empresa: string;
  cuit: string;
  cuitRepresentado: string;
  ambiente: "homologacion" | "produccion";
  activo: boolean;
  claveFiscal: string;
}

const initialForm: FormData = {
  empresa: "",
  cuit: "",
  cuitRepresentado: "",
  ambiente: "homologacion",
  activo: true,
  claveFiscal: "",
};

export function ClientEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = !id || id === "nuevo";
  const parsedId = Number(id);
  const clientId = isNew || !Number.isFinite(parsedId) ? 0 : parsedId;

  const clientQuery = useClientQuery(clientId);
  const updateMutation = useUpdateClientMutation();
  const createMutation = useCreateClientMutation();

  const [form, setForm] = useState<FormData>(initialForm);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (clientQuery.data && !isNew) {
      setForm({
        empresa: clientQuery.data.empresa,
        cuit: clientQuery.data.cuit,
        cuitRepresentado: clientQuery.data.cuitRepresentado,
        ambiente: clientQuery.data.ambiente,
        activo: clientQuery.data.activo,
        claveFiscal: "",
      });
    }
  }, [clientQuery.data, isNew]);

  function handleChange(field: keyof FormData, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    try {
      if (isNew) {
        await createMutation.mutateAsync({
          empresa: form.empresa.trim(),
          cuit: form.cuit.trim(),
          cuit_representado: form.cuitRepresentado.trim(),
          ambiente: form.ambiente,
          activo: form.activo,
          clave_fiscal: form.claveFiscal.trim(),
        });
      } else {
        await updateMutation.mutateAsync({
          clientId,
          input: {
            empresa: form.empresa.trim(),
            cuit: form.cuit.trim(),
            cuit_representado: form.cuitRepresentado.trim(),
            ambiente: form.ambiente,
            activo: form.activo,
            ...(form.claveFiscal.trim() ? { clave_fiscal: form.claveFiscal.trim() } : {}),
          },
        });
      }
      navigate("/clientes");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al guardar");
    }
  }

  const isLoading = clientQuery.isLoading && !isNew;
  const isSaving = updateMutation.isPending || createMutation.isPending;

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={isNew ? "Nuevo Cliente" : "Editar Cliente"}
        subtitle={isNew ? undefined : form.empresa}
      />

      <Card className="max-w-2xl" padding="none">
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error ? <Alert variant="error">{error}</Alert> : null}

          <Input
            label="Empresa"
            value={form.empresa}
            onChange={(e) => handleChange("empresa", e.target.value)}
            required
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="CUIT"
              value={form.cuit}
              onChange={(e) => handleChange("cuit", e.target.value)}
              placeholder="20123456789"
              required
            />
            <Input
              label="CUIT Representado"
              value={form.cuitRepresentado}
              onChange={(e) => handleChange("cuitRepresentado", e.target.value)}
              placeholder="20123456789"
              required
            />
          </div>

          <Select
            label="Ambiente"
            value={form.ambiente}
            onChange={(e) => handleChange("ambiente", e.target.value as "homologacion" | "produccion")}
            options={[
              { value: "homologacion", label: "Homologación" },
              { value: "produccion", label: "Producción" },
            ]}
          />

          <Input
            label={isNew ? "Clave Fiscal" : "Nueva Clave Fiscal (dejar vacío para mantener)"}
            type="password"
            value={form.claveFiscal}
            onChange={(e) => handleChange("claveFiscal", e.target.value)}
            required={isNew}
          />

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="activo"
              checked={form.activo}
              onChange={(e) => handleChange("activo", e.target.checked)}
              className="h-4 w-4 text-green-600 rounded border-slate-300"
            />
            <label htmlFor="activo" className="text-sm text-slate-700">
              Cliente activo
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <Button
              type="button"
              variant="secondary"
              onClick={() => navigate(-1)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button type="submit" isLoading={isSaving}>
              {isNew ? "Crear Cliente" : "Guardar Cambios"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
