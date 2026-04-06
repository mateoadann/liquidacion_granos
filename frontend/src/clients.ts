import { fetchWithAuth } from "./api/client";

export type ClientEnvironment = "homologacion" | "produccion";

export interface Client {
  id: number;
  empresa: string;
  cuit: string;
  cuitRepresentado: string;
  ambiente: ClientEnvironment;
  activo: boolean;
  playwrightEnabled: boolean;
  claveFiscalCargada: boolean;
  certificadosCargados: boolean;
  certFileName: string | null;
  keyFileName: string | null;
  certUploadedAt: string | null;
}

export interface CreateClientInput {
  empresa: string;
  cuit: string;
  cuit_representado: string;
  ambiente: ClientEnvironment;
  clave_fiscal: string;
  activo?: boolean;
}

export interface UpdateClientInput {
  empresa?: string;
  cuit?: string;
  cuit_representado?: string;
  ambiente?: ClientEnvironment;
  clave_fiscal?: string;
  activo?: boolean;
}

export interface UploadCertificatesInput {
  clientId: number;
  certFile: File;
  keyFile: File;
}

export interface ClientCertificateMeta {
  certFileName: string | null;
  keyFileName: string | null;
  uploadedAt: string | null;
  message: string | null;
}

export interface ClientValidationResult {
  ready: boolean;
  statusText: string;
  checks: Record<string, boolean>;
}

export interface CertTestServiceResult {
  ok: boolean;
  message: string;
  razonSocial?: string;
}

export interface CertTestResult {
  config: {
    ok: boolean;
    checks: Record<string, boolean>;
  };
  wslpg: CertTestServiceResult;
  constancia: CertTestServiceResult;
  certificate_info: {
    subject: string;
    issuer: string;
    not_before: string;
    not_after: string;
    expired: boolean;
  } | null;
}

export interface RunPlaywrightPipelineInput {
  fechaDesde: string;
  fechaHasta: string;
  taxpayerIds?: number[];
  timeoutMs?: number;
  typeDelayMs?: number;
}

export interface PlaywrightTaxpayerRunResult {
  taxpayerId: number;
  empresa: string;
  ok: boolean;
  error: string | null;
  totalCoesDetectados: number;
  totalCoesNuevos: number;
  totalOmitidosExistentes: number;
  totalProcesadosOk: number;
  totalProcesadosError: number;
}

export interface PlaywrightPipelineRunResult {
  startedAt: string;
  finishedAt: string;
  fechaDesde: string;
  fechaHasta: string;
  taxpayersTotal: number;
  taxpayersOk: number;
  taxpayersError: number;
  results: PlaywrightTaxpayerRunResult[];
}

export type PlaywrightClientProgressStatus = "pending" | "running" | "done" | "error";

export interface PlaywrightClientProgress {
  taxpayerId: number;
  empresa: string;
  status: PlaywrightClientProgressStatus;
  error: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  totalCoesDetectados: number;
  totalCoesNuevos: number;
  totalProcesadosOk: number;
  totalProcesadosError: number;
}

export interface PlaywrightJobProgress {
  totalClients: number;
  completedClients: number;
  runningClientId: number | null;
  clients: PlaywrightClientProgress[];
}

export type PlaywrightJobStatus = "pending" | "running" | "completed" | "failed";

export interface PlaywrightPipelineJob {
  id: number;
  operation: string;
  status: PlaywrightJobStatus;
  payload: Record<string, unknown> | null;
  progress: PlaywrightJobProgress | null;
  result: PlaywrightPipelineRunResult | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  updatedAt: string | null;
}

export interface DownloadClientCoesInput {
  clientId: number;
  fechaDesde?: string;
  fechaHasta?: string;
}

export interface DownloadFileResult {
  blob: Blob;
  fileName: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

type JsonRecord = Record<string, unknown>;

const CHECK_KEYS = [
  "empresa_cargada",
  "cuit_valido",
  "cuit_representado_valido",
  "clave_fiscal_cargada",
  "certificados_cargados",
  "certificados_validos",
] as const;

const CHECK_KEY_MAP: Record<(typeof CHECK_KEYS)[number], string[]> = {
  empresa_cargada: ["empresa_cargada", "has_empresa"],
  cuit_valido: ["cuit_valido", "has_cuit"],
  cuit_representado_valido: ["cuit_representado_valido", "has_cuit_representado"],
  clave_fiscal_cargada: ["clave_fiscal_cargada", "has_clave_fiscal"],
  certificados_cargados: ["certificados_cargados", "has_certificates"],
  certificados_validos: ["certificados_validos", "certificates_valid"],
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function parseApiError(raw: unknown, fallback: string): string {
  if (isRecord(raw)) {
    const fromError = raw.error;
    if (typeof fromError === "string" && fromError.trim()) {
      return fromError;
    }

    const fromMessage = raw.message;
    if (typeof fromMessage === "string" && fromMessage.trim()) {
      return fromMessage;
    }
  }

  if (typeof raw === "string" && raw.trim()) {
    return raw;
  }

  return fallback;
}

async function readResponseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetchWithAuth(path, init);
  const payload = await readResponseBody(res);

  if (!res.ok) {
    throw new Error(parseApiError(payload, "Error en solicitud al backend"));
  }

  return payload as T;
}

function normalizeClient(raw: unknown): Client {
  const data = isRecord(raw) ? raw : {};
  const credentials = isRecord(data.credentials) ? data.credentials : {};

  const certFileName =
    asNullableString(data.cert_crt_filename) ?? asNullableString(data.cert_file_name);
  const keyFileName =
    asNullableString(data.cert_key_filename) ?? asNullableString(data.key_file_name);

  const claveFiscalCargada =
    asBoolean(data.clave_fiscal_cargada) ||
    asBoolean(credentials.clave_fiscal_cargada) ||
    asBoolean(data.has_clave_fiscal);

  const certificadosCargados =
    asBoolean(data.certificados_cargados) ||
    asBoolean(credentials.certificados_cargados) ||
    Boolean(certFileName && keyFileName);

  return {
    id: Number(data.id ?? 0),
    empresa: asString(data.empresa || data.razon_social || ""),
    cuit: asString(data.cuit),
    cuitRepresentado: asString(data.cuit_representado),
    ambiente: asString(data.ambiente) === "produccion" ? "produccion" : "homologacion",
    activo: asBoolean(data.activo, true),
    playwrightEnabled: asBoolean(data.playwright_enabled, true),
    claveFiscalCargada,
    certificadosCargados,
    certFileName,
    keyFileName,
    certUploadedAt: asNullableString(data.cert_uploaded_at),
  };
}

function normalizeValidation(raw: unknown): ClientValidationResult {
  const data = isRecord(raw) ? raw : {};
  const checksData = isRecord(data.checks) ? data.checks : {};

  const checks: Record<string, boolean> = {};
  for (const key of CHECK_KEYS) {
    const aliases = CHECK_KEY_MAP[key] ?? [key];
    checks[key] = aliases.some((alias) => {
      const fromChecks = checksData[alias];
      const fromRoot = data[alias];
      return asBoolean(fromChecks) || asBoolean(fromRoot);
    });
  }

  const readyFromResponse =
    data.ready ??
    data.listo_para_playwright ??
    data.playwright_ready ??
    data.ready_for_playwright;
  const ready =
    typeof readyFromResponse === "boolean"
      ? readyFromResponse
      : Object.values(checks).every(Boolean);

  const statusText = ready ? "Listo para Playwright" : "Configuración incompleta";

  return { ready, statusText, checks };
}

function normalizeCertificatesMeta(raw: unknown): ClientCertificateMeta {
  const data = isRecord(raw) ? raw : {};
  const nestedClient = isRecord(data.client) ? data.client : {};
  const nestedStorage = isRecord(data.certificates) ? data.certificates : {};

  return {
    certFileName:
      asNullableString(data.cert_crt_filename) ??
      asNullableString(data.cert_file_name) ??
      asNullableString(nestedClient.cert_crt_filename),
    keyFileName:
      asNullableString(data.cert_key_filename) ??
      asNullableString(data.key_file_name) ??
      asNullableString(nestedClient.cert_key_filename),
    uploadedAt:
      asNullableString(data.cert_uploaded_at) ??
      asNullableString(data.uploaded_at) ??
      asNullableString(nestedClient.cert_uploaded_at) ??
      asNullableString(nestedStorage.detected_uploaded_at),
    message:
      asNullableString(data.message) ??
      (asBoolean(nestedStorage.has_certificates)
        ? "Certificados cargados correctamente."
        : null),
  };
}

function normalizePlaywrightTaxpayerRunResult(raw: unknown): PlaywrightTaxpayerRunResult {
  const data = isRecord(raw) ? raw : {};
  return {
    taxpayerId: asNumber(data.taxpayer_id),
    empresa: asString(data.empresa),
    ok: asBoolean(data.ok),
    error: asNullableString(data.error),
    totalCoesDetectados: asNumber(data.total_coes_detectados),
    totalCoesNuevos: asNumber(data.total_coes_nuevos),
    totalOmitidosExistentes: asNumber(data.total_omitidos_existentes),
    totalProcesadosOk: asNumber(data.total_procesados_ok),
    totalProcesadosError: asNumber(data.total_procesados_error),
  };
}

function normalizePlaywrightPipelineRun(raw: unknown): PlaywrightPipelineRunResult {
  const data = isRecord(raw) ? raw : {};
  const rawResults = Array.isArray(data.results) ? data.results : [];
  return {
    startedAt: asString(data.started_at),
    finishedAt: asString(data.finished_at),
    fechaDesde: asString(data.fecha_desde),
    fechaHasta: asString(data.fecha_hasta),
    taxpayersTotal: asNumber(data.taxpayers_total),
    taxpayersOk: asNumber(data.taxpayers_ok),
    taxpayersError: asNumber(data.taxpayers_error),
    results: rawResults.map(normalizePlaywrightTaxpayerRunResult),
  };
}

function normalizePlaywrightClientProgress(raw: unknown): PlaywrightClientProgress {
  const data = isRecord(raw) ? raw : {};
  const metrics = isRecord(data.metrics) ? data.metrics : {};
  const rawStatus = asString(data.status, "pending");
  const status: PlaywrightClientProgressStatus =
    rawStatus === "running" || rawStatus === "done" || rawStatus === "error"
      ? rawStatus
      : "pending";

  return {
    taxpayerId: asNumber(data.taxpayer_id),
    empresa: asString(data.empresa),
    status,
    error: asNullableString(data.error),
    startedAt: asNullableString(data.started_at),
    finishedAt: asNullableString(data.finished_at),
    totalCoesDetectados: asNumber(metrics.total_coes_detectados),
    totalCoesNuevos: asNumber(metrics.total_coes_nuevos),
    totalProcesadosOk: asNumber(metrics.total_procesados_ok),
    totalProcesadosError: asNumber(metrics.total_procesados_error),
  };
}

function normalizePlaywrightJobProgress(raw: unknown): PlaywrightJobProgress | null {
  const data = isRecord(raw) ? raw : null;
  if (!data) return null;
  const rawClients = Array.isArray(data.clients) ? data.clients : [];

  return {
    totalClients: asNumber(data.total_clients),
    completedClients: asNumber(data.completed_clients),
    runningClientId: data.running_client_id === null ? null : asNumber(data.running_client_id, 0),
    clients: rawClients.map(normalizePlaywrightClientProgress),
  };
}

function normalizePlaywrightPipelineJob(raw: unknown): PlaywrightPipelineJob {
  const data = isRecord(raw) ? raw : {};
  const rawStatus = asString(data.status, "pending");
  const status: PlaywrightJobStatus =
    rawStatus === "running" || rawStatus === "completed" || rawStatus === "failed"
      ? rawStatus
      : "pending";

  const rawPayload = isRecord(data.payload) ? data.payload : null;
  const rawResult = data.result;

  return {
    id: asNumber(data.id),
    operation: asString(data.operation),
    status,
    payload: rawPayload,
    progress: normalizePlaywrightJobProgress(rawPayload?.progress),
    result: rawResult ? normalizePlaywrightPipelineRun(rawResult) : null,
    errorMessage: asNullableString(data.error_message),
    createdAt: asString(data.created_at),
    startedAt: asNullableString(data.started_at),
    finishedAt: asNullableString(data.finished_at),
    updatedAt: asNullableString(data.updated_at),
  };
}

export async function listClients(): Promise<Client[]> {
  const payload = await requestJson<unknown>("/clients", { method: "GET" });
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload.map(normalizeClient);
}

export async function getClient(clientId: number): Promise<Client> {
  const payload = await requestJson<unknown>(`/clients/${clientId}`, { method: "GET" });
  return normalizeClient(payload);
}

export async function createClient(input: CreateClientInput): Promise<Client> {
  const payload = await requestJson<unknown>("/clients", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  return normalizeClient(payload);
}

export async function updateClient(
  clientId: number,
  input: UpdateClientInput
): Promise<Client> {
  const payload = await requestJson<unknown>(`/clients/${clientId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  return normalizeClient(payload);
}

export async function deleteClient(clientId: number): Promise<void> {
  await requestJson<unknown>(`/clients/${clientId}`, {
    method: "DELETE",
  });
}

export async function uploadClientCertificates(
  input: UploadCertificatesInput
): Promise<ClientCertificateMeta> {
  const formData = new FormData();
  formData.append("cert_file", input.certFile);
  formData.append("key_file", input.keyFile);

  const payload = await requestJson<unknown>(`/clients/${input.clientId}/certificates`, {
    method: "POST",
    body: formData,
  });

  return normalizeCertificatesMeta(payload);
}

export async function validateClientConfig(
  clientId: number
): Promise<ClientValidationResult> {
  const payload = await requestJson<unknown>(`/clients/${clientId}/validate-config`, {
    method: "POST",
  });

  return normalizeValidation(payload);
}

export async function testClientCertificates(
  clientId: number
): Promise<CertTestResult> {
  return requestJson<CertTestResult>(`/clients/${clientId}/test-certificates`, {
    method: "POST",
  });
}

export async function generateClientCsr(
  clientId: number,
  nombreCertificado: string
): Promise<Blob> {
  const res = await fetchWithAuth(`/clients/${clientId}/generate-csr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nombre_certificado: nombreCertificado }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as Record<string, string>)?.error ?? "Error al generar CSR");
  }
  return res.blob();
}

export async function runPlaywrightPipeline(
  input: RunPlaywrightPipelineInput
): Promise<PlaywrightPipelineJob> {
  const payload = await requestJson<unknown>("/playwright/lpg/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      fecha_desde: input.fechaDesde,
      fecha_hasta: input.fechaHasta,
      taxpayer_ids: input.taxpayerIds,
      timeout_ms: input.timeoutMs,
      type_delay_ms: input.typeDelayMs,
    }),
  });

  const data = isRecord(payload) ? payload : {};
  return normalizePlaywrightPipelineJob(data.job);
}

export async function getPlaywrightPipelineJob(jobId: number): Promise<PlaywrightPipelineJob> {
  const payload = await requestJson<unknown>(`/playwright/lpg/jobs/${jobId}`, {
    method: "GET",
  });
  return normalizePlaywrightPipelineJob(payload);
}

function resolveDownloadFileName(contentDisposition: string | null, fallback: string): string {
  const header = contentDisposition ?? "";
  const utfMatch = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch?.[1]) {
    return decodeURIComponent(utfMatch[1]);
  }
  const asciiMatch = header.match(/filename="?([^";]+)"?/i);
  if (asciiMatch?.[1]) {
    return asciiMatch[1];
  }
  return fallback;
}

export async function downloadClientCoesExport(
  input: DownloadClientCoesInput
): Promise<DownloadFileResult> {
  const params = new URLSearchParams();
  if (input.fechaDesde) params.set("fecha_desde", input.fechaDesde);
  if (input.fechaHasta) params.set("fecha_hasta", input.fechaHasta);

  const qs = params.toString();
  const url = `/clients/${input.clientId}/coes/export${qs ? `?${qs}` : ""}`;

  const res = await fetchWithAuth(url, { method: "GET" });

  if (!res.ok) {
    const payload = await readResponseBody(res);
    throw new Error(parseApiError(payload, "No se pudo descargar el archivo"));
  }

  const blob = await res.blob();
  const fallbackName = `coes_cliente_${input.clientId}.xlsx`;
  const fileName = resolveDownloadFileName(res.headers.get("content-disposition"), fallbackName);
  return { blob, fileName };
}
