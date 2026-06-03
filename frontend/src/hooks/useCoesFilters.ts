import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export type Controlada = "" | "true" | "false";
export type TipoCte = "F1" | "F2" | "NL";

const ALL_TIPO_CTE: TipoCte[] = ["F1", "F2", "NL"];

export interface CoesFilters {
  search: string;
  taxpayerId: number | undefined;
  estadoCiclo: string;
  fechaDesde: string;
  fechaHasta: string;
  controlada: Controlada;
  tipoCte: TipoCte[];
  periodoMes: string;
  periodoAnio: string;
}

export interface UseCoesFiltersResult extends CoesFilters {
  setSearch: (value: string) => void;
  setTaxpayerId: (value: number | undefined) => void;
  setEstadoCiclo: (value: string) => void;
  setFechaDesde: (value: string) => void;
  setFechaHasta: (value: string) => void;
  setControlada: (value: Controlada) => void;
  setTipoCte: (value: TipoCte[]) => void;
  toggleTipoCte: (value: TipoCte) => void;
  setPeriodo: (mes: string, anio: string) => void;
  clearAll: () => void;
  hasActiveFilters: boolean;
  drawerFilterCount: number;
}

const FILTER_KEYS = [
  "search",
  "taxpayer_id",
  "estado_ciclo",
  "fecha_desde",
  "fecha_hasta",
  "controlada",
  "tipo_cte",
  "periodo_mes",
  "periodo_anio",
] as const;

function parseTaxpayerId(raw: string | null): number | undefined {
  if (!raw) return undefined;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function parseControlada(raw: string | null): Controlada {
  if (raw === "true" || raw === "false") return raw;
  return "";
}

function parseTipoCte(raw: string | null): TipoCte[] {
  if (!raw) return [];
  const seen = new Set<TipoCte>();
  for (const part of raw.split(",")) {
    const v = part.trim().toUpperCase();
    if ((ALL_TIPO_CTE as string[]).includes(v)) {
      seen.add(v as TipoCte);
    }
  }
  return ALL_TIPO_CTE.filter((t) => seen.has(t));
}

function parseMes(raw: string | null): string {
  if (!raw) return "";
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1 || n > 12) return "";
  return String(n);
}

function parseAnio(raw: string | null): string {
  if (!raw) return "";
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 2000 || n > 2100) return "";
  return String(n);
}

function lastDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function useCoesFilters(): UseCoesFiltersResult {
  const [searchParams, setSearchParams] = useSearchParams();

  const search = searchParams.get("search") ?? "";
  const taxpayerId = parseTaxpayerId(searchParams.get("taxpayer_id"));
  const estadoCiclo = searchParams.get("estado_ciclo") ?? "";
  const fechaDesde = searchParams.get("fecha_desde") ?? "";
  const fechaHasta = searchParams.get("fecha_hasta") ?? "";
  const controlada = parseControlada(searchParams.get("controlada"));
  const tipoCte = parseTipoCte(searchParams.get("tipo_cte"));
  const periodoMes = parseMes(searchParams.get("periodo_mes"));
  const periodoAnio = parseAnio(searchParams.get("periodo_anio"));

  const updateParam = useCallback(
    (key: string, value: string | undefined, extraDeletes: string[] = []) => {
      setSearchParams(
        (prev) => {
          const updated = new URLSearchParams(prev);
          if (value === undefined || value === "") {
            updated.delete(key);
          } else {
            updated.set(key, value);
          }
          updated.delete("page");
          for (const extra of extraDeletes) updated.delete(extra);
          return updated;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setSearch = useCallback(
    (value: string) => updateParam("search", value),
    [updateParam],
  );

  const setTaxpayerId = useCallback(
    (value: number | undefined) =>
      updateParam("taxpayer_id", value !== undefined ? String(value) : undefined),
    [updateParam],
  );

  const setEstadoCiclo = useCallback(
    (value: string) => updateParam("estado_ciclo", value),
    [updateParam],
  );

  // Editar fechas manualmente limpia el periodo (ya no representa el mes completo).
  const setFechaDesde = useCallback(
    (value: string) => {
      const shouldClearHasta = !!value && !!fechaHasta && value > fechaHasta;
      const extras = ["periodo_mes", "periodo_anio"];
      if (shouldClearHasta) extras.push("fecha_hasta");
      updateParam("fecha_desde", value, extras);
    },
    [updateParam, fechaHasta],
  );

  const setFechaHasta = useCallback(
    (value: string) =>
      updateParam("fecha_hasta", value, ["periodo_mes", "periodo_anio"]),
    [updateParam],
  );

  const setControlada = useCallback(
    (value: Controlada) => updateParam("controlada", value),
    [updateParam],
  );

  const setTipoCte = useCallback(
    (value: TipoCte[]) => {
      const normalized = ALL_TIPO_CTE.filter((t) => value.includes(t));
      updateParam("tipo_cte", normalized.length > 0 ? normalized.join(",") : "");
    },
    [updateParam],
  );

  const toggleTipoCte = useCallback(
    (value: TipoCte) => {
      const next = tipoCte.includes(value)
        ? tipoCte.filter((t) => t !== value)
        : [...tipoCte, value];
      setTipoCte(next);
    },
    [tipoCte, setTipoCte],
  );

  // setPeriodo persiste mes/año (parcial o completo) en la URL.
  // Solo deriva fecha_desde/fecha_hasta cuando ambos son válidos.
  // Si uno se borra, limpia las fechas derivadas pero mantiene el otro.
  const setPeriodo = useCallback(
    (mes: string, anio: string) => {
      setSearchParams(
        (prev) => {
          const updated = new URLSearchParams(prev);
          updated.delete("page");
          const mesNum = Number.parseInt(mes, 10);
          const anioNum = Number.parseInt(anio, 10);
          const validMes = Number.isFinite(mesNum) && mesNum >= 1 && mesNum <= 12;
          const validAnio = Number.isFinite(anioNum) && anioNum >= 2000 && anioNum <= 2100;

          if (validMes) updated.set("periodo_mes", String(mesNum));
          else updated.delete("periodo_mes");

          if (validAnio) updated.set("periodo_anio", String(anioNum));
          else updated.delete("periodo_anio");

          if (validMes && validAnio) {
            const last = lastDayOfMonth(anioNum, mesNum);
            updated.set("fecha_desde", `${anioNum}-${pad2(mesNum)}-01`);
            updated.set("fecha_hasta", `${anioNum}-${pad2(mesNum)}-${pad2(last)}`);
          } else {
            updated.delete("fecha_desde");
            updated.delete("fecha_hasta");
          }
          return updated;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const clearAll = useCallback(() => {
    setSearchParams(
      (prev) => {
        const updated = new URLSearchParams(prev);
        for (const key of FILTER_KEYS) updated.delete(key);
        updated.delete("page");
        return updated;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  const periodoActive = !!periodoMes && !!periodoAnio;
  const drawerFilterCount =
    (taxpayerId !== undefined ? 1 : 0) +
    (estadoCiclo ? 1 : 0) +
    (periodoActive ? 1 : fechaDesde || fechaHasta ? 1 : 0) +
    (controlada ? 1 : 0) +
    (tipoCte.length > 0 ? 1 : 0);

  const hasActiveFilters = !!search || drawerFilterCount > 0;

  return useMemo(
    () => ({
      search,
      taxpayerId,
      estadoCiclo,
      fechaDesde,
      fechaHasta,
      controlada,
      tipoCte,
      periodoMes,
      periodoAnio,
      setSearch,
      setTaxpayerId,
      setEstadoCiclo,
      setFechaDesde,
      setFechaHasta,
      setControlada,
      setTipoCte,
      toggleTipoCte,
      setPeriodo,
      clearAll,
      hasActiveFilters,
      drawerFilterCount,
    }),
    [
      search,
      taxpayerId,
      estadoCiclo,
      fechaDesde,
      fechaHasta,
      controlada,
      tipoCte,
      periodoMes,
      periodoAnio,
      setSearch,
      setTaxpayerId,
      setEstadoCiclo,
      setFechaDesde,
      setFechaHasta,
      setControlada,
      setTipoCte,
      toggleTipoCte,
      setPeriodo,
      clearAll,
      hasActiveFilters,
      drawerFilterCount,
    ],
  );
}
