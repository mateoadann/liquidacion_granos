import { useState } from "react";
import { Alert, Button, Combobox, Input, Modal, Spinner } from "../ui";
import { useConsultManualCoe, useCreateManualCoe } from "../../hooks/useCoes";
import { useClientsQuery } from "../../useClients";
import { downloadConsultedCoePdf, type CoePreview } from "../../api/coes";
import { DatosLimpiosSection } from "./dataDisplay";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

interface ConsultedData {
  preview: CoePreview;
  tipoDocumento: "LPG" | "AJUSTE";
  duplicado: boolean;
  coeId: number | null;
}

type ModalState =
  | { kind: "idle" }
  | { kind: "consulting" }
  | { kind: "consult-error"; message: string }
  | ({ kind: "consulted" } & ConsultedData)
  | ({ kind: "loading" } & ConsultedData)
  | ({ kind: "load-error"; message: string } & ConsultedData)
  | { kind: "loaded" };

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CoeManualLoadModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CoeManualLoadModal({ isOpen, onClose }: CoeManualLoadModalProps) {
  const [state, setState] = useState<ModalState>({ kind: "idle" });
  const [coe, setCoe] = useState("");
  const [taxpayerId, setTaxpayerId] = useState("");
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  async function handleDownloadPdf() {
    if (!coe.trim() || !taxpayerId) return;
    setDownloadingPdf(true);
    try {
      const blob = await downloadConsultedCoePdf({
        coe: coe.trim(),
        taxpayer_id: Number(taxpayerId),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `liquidacion_${coe.trim()}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Error al descargar PDF");
    } finally {
      setDownloadingPdf(false);
    }
  }

  const clientsQuery = useClientsQuery();
  const clients = clientsQuery.data ?? [];

  const consultMutation = useConsultManualCoe();
  const createMutation = useCreateManualCoe();

  function handleClose() {
    setState({ kind: "idle" });
    setCoe("");
    setTaxpayerId("");
    onClose();
  }

  async function handleConsultar() {
    if (!coe.trim() || !taxpayerId) return;

    setState({ kind: "consulting" });
    try {
      const result = await consultMutation.mutateAsync({
        coe: coe.trim(),
        taxpayer_id: Number(taxpayerId),
      });
      setState({
        kind: "consulted",
        preview: result.preview,
        tipoDocumento: result.tipo_documento,
        duplicado: result.duplicado,
        coeId: result.coe_id,
      });
    } catch (err) {
      setState({
        kind: "consult-error",
        message: err instanceof Error ? err.message : "Error al consultar",
      });
    }
  }

  async function handleCargar() {
    if (state.kind !== "consulted" && state.kind !== "load-error") {
      return;
    }

    const { preview, tipoDocumento, duplicado, coeId } = state;
    setState({ kind: "loading", preview, tipoDocumento, duplicado, coeId });

    try {
      await createMutation.mutateAsync({
        coe: coe.trim(),
        taxpayer_id: Number(taxpayerId),
      });
      setState({ kind: "loaded" });
      setTimeout(handleClose, 800);
    } catch (err) {
      setState({
        kind: "load-error",
        preview,
        tipoDocumento,
        duplicado,
        coeId,
        message: err instanceof Error ? err.message : "Error al cargar",
      });
    }
  }

  const isConsulting = state.kind === "consulting";
  const isLoading = state.kind === "loading";

  // Step 1: idle | consulting | consult-error
  const showStep1 =
    state.kind === "idle" ||
    state.kind === "consulting" ||
    state.kind === "consult-error";

  // Step 2: consulted | loading | load-error | loaded
  const showStep2 =
    state.kind === "consulted" ||
    state.kind === "loading" ||
    state.kind === "load-error" ||
    state.kind === "loaded";

  const cargarDisabled =
    isLoading ||
    (state.kind === "consulted" && state.duplicado) ||
    (state.kind === "load-error" && state.duplicado);

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Cargar COE manual"
      size="7xl"
      footer={
        showStep1 ? (
          <>
            <Button variant="secondary" onClick={handleClose} disabled={isConsulting}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={handleConsultar}
              isLoading={isConsulting}
              disabled={!coe.trim() || !taxpayerId || isConsulting}
            >
              Consultar
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={handleClose} disabled={isLoading}>
              Cerrar
            </Button>
            <Button
              variant="secondary"
              onClick={handleDownloadPdf}
              isLoading={downloadingPdf}
              disabled={
                isLoading ||
                downloadingPdf ||
                state.kind === "loaded"
              }
            >
              PDF
            </Button>
            <Button
              variant="primary"
              onClick={handleCargar}
              isLoading={isLoading}
              disabled={cargarDisabled}
            >
              Cargar esta liquidación
            </Button>
          </>
        )
      }
    >
      {showStep1 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Número de COE
            </label>
            <Input
              type="text"
              placeholder="Ej: 330130301001"
              value={coe}
              onChange={(e) => setCoe(e.target.value)}
              disabled={isConsulting}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Cliente
            </label>
            <Combobox
              value={taxpayerId}
              onChange={setTaxpayerId}
              options={clients.map((c) => ({
                value: c.id.toString(),
                label: c.empresa,
              }))}
              placeholder="Seleccionar cliente..."
            />
          </div>

          {state.kind === "consult-error" && (
            <Alert variant="error">{state.message}</Alert>
          )}
        </div>
      )}

      {showStep2 && (
        <div className="max-h-[75vh] overflow-y-auto pr-1 space-y-4">
          {state.kind === "loaded" ? (
            <Alert variant="success">
              COE cargado exitosamente. Cerrando...
            </Alert>
          ) : (
            <>
              {(state.kind === "consulted" ||
                state.kind === "loading" ||
                state.kind === "load-error") && (
                <>
                  {state.duplicado && (
                    <Alert variant="warning">
                      Esta liquidación ya está cargada.{" "}
                      {state.coeId !== null && (
                        <a
                          href={`/coes/${state.coeId}`}
                          className="underline font-medium"
                          target="_blank"
                          rel="noreferrer"
                        >
                          Ver COE #{state.coeId}
                        </a>
                      )}
                    </Alert>
                  )}
                  <DatosLimpiosSection
                    rawData={state.preview.raw_data ?? {}}
                    datosLimpios={state.preview.datos_limpios}
                    taxpayerId={Number(taxpayerId) || null}
                  />
                </>
              )}

              {state.kind === "loading" && (
                <div className="flex justify-center py-2">
                  <Spinner size="sm" />
                </div>
              )}

              {state.kind === "load-error" && (
                <Alert variant="error">{state.message}</Alert>
              )}
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
