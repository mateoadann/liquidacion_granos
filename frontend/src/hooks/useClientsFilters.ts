import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export type ActiveFilter = "" | "true" | "false";
export type HasCertsFilter = "" | "true" | "false";
export type OrderBy = "id" | "empresa";

export interface ClientsFilters {
  search: string;
  active: ActiveFilter;
  hasCertificates: HasCertsFilter;
  orderBy: OrderBy;
}

export interface UseClientsFiltersResult extends ClientsFilters {
  setSearch: (value: string) => void;
  setActive: (value: ActiveFilter) => void;
  setHasCertificates: (value: HasCertsFilter) => void;
  setOrderBy: (value: OrderBy) => void;
  clearAll: () => void;
  hasActiveFilters: boolean;
  drawerFilterCount: number;
}

const FILTER_KEYS = ["search", "active", "has_certificates", "order_by"] as const;

function parseTriState(raw: string | null): "" | "true" | "false" {
  if (raw === "true" || raw === "false") return raw;
  return "";
}

function parseOrderBy(raw: string | null): OrderBy {
  return raw === "empresa" ? "empresa" : "id";
}

export function useClientsFilters(): UseClientsFiltersResult {
  const [searchParams, setSearchParams] = useSearchParams();

  const search = searchParams.get("search") ?? "";
  const active = parseTriState(searchParams.get("active"));
  const hasCertificates = parseTriState(searchParams.get("has_certificates"));
  const orderBy = parseOrderBy(searchParams.get("order_by"));

  const updateParam = useCallback(
    (key: string, value: string | undefined) => {
      setSearchParams(
        (prev) => {
          const updated = new URLSearchParams(prev);
          if (value === undefined || value === "") {
            updated.delete(key);
          } else {
            updated.set(key, value);
          }
          updated.delete("page");
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

  const setActive = useCallback(
    (value: ActiveFilter) => updateParam("active", value),
    [updateParam],
  );

  const setHasCertificates = useCallback(
    (value: HasCertsFilter) => updateParam("has_certificates", value),
    [updateParam],
  );

  const setOrderBy = useCallback(
    (value: OrderBy) => updateParam("order_by", value === "id" ? "" : value),
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
    (active ? 1 : 0) +
    (hasCertificates ? 1 : 0) +
    (orderBy !== "id" ? 1 : 0);
  const hasActiveFilters = !!search || drawerFilterCount > 0;

  return useMemo(
    () => ({
      search,
      active,
      hasCertificates,
      orderBy,
      setSearch,
      setActive,
      setHasCertificates,
      setOrderBy,
      clearAll,
      hasActiveFilters,
      drawerFilterCount,
    }),
    [
      search,
      active,
      hasCertificates,
      orderBy,
      setSearch,
      setActive,
      setHasCertificates,
      setOrderBy,
      clearAll,
      hasActiveFilters,
      drawerFilterCount,
    ],
  );
}
