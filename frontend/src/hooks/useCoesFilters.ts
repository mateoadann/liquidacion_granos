import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export type Controlada = "" | "true" | "false";

export interface CoesFilters {
  search: string;
  taxpayerId: number | undefined;
  estadoCiclo: string;
  fechaDesde: string;
  fechaHasta: string;
  controlada: Controlada;
}

export interface UseCoesFiltersResult extends CoesFilters {
  setSearch: (value: string) => void;
  setTaxpayerId: (value: number | undefined) => void;
  setEstadoCiclo: (value: string) => void;
  setFechaDesde: (value: string) => void;
  setFechaHasta: (value: string) => void;
  setControlada: (value: Controlada) => void;
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

export function useCoesFilters(): UseCoesFiltersResult {
  const [searchParams, setSearchParams] = useSearchParams();

  const search = searchParams.get("search") ?? "";
  const taxpayerId = parseTaxpayerId(searchParams.get("taxpayer_id"));
  const estadoCiclo = searchParams.get("estado_ciclo") ?? "";
  const fechaDesde = searchParams.get("fecha_desde") ?? "";
  const fechaHasta = searchParams.get("fecha_hasta") ?? "";
  const controlada = parseControlada(searchParams.get("controlada"));

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

  const setFechaDesde = useCallback(
    (value: string) => {
      const shouldClearHasta = !!value && !!fechaHasta && value > fechaHasta;
      updateParam("fecha_desde", value, shouldClearHasta ? ["fecha_hasta"] : []);
    },
    [updateParam, fechaHasta],
  );

  const setFechaHasta = useCallback(
    (value: string) => updateParam("fecha_hasta", value),
    [updateParam],
  );

  const setControlada = useCallback(
    (value: Controlada) => updateParam("controlada", value),
    [updateParam],
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

  const drawerFilterCount =
    (taxpayerId !== undefined ? 1 : 0) +
    (estadoCiclo ? 1 : 0) +
    (fechaDesde || fechaHasta ? 1 : 0) +
    (controlada ? 1 : 0);

  const hasActiveFilters = !!search || drawerFilterCount > 0;

  return useMemo(
    () => ({
      search,
      taxpayerId,
      estadoCiclo,
      fechaDesde,
      fechaHasta,
      controlada,
      setSearch,
      setTaxpayerId,
      setEstadoCiclo,
      setFechaDesde,
      setFechaHasta,
      setControlada,
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
      setSearch,
      setTaxpayerId,
      setEstadoCiclo,
      setFechaDesde,
      setFechaHasta,
      setControlada,
      clearAll,
      hasActiveFilters,
      drawerFilterCount,
    ],
  );
}
