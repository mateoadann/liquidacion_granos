import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useCoesFilters } from "../useCoesFilters";

function makeWrapper(initialEntries: string[] = ["/coes"]) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>;
  };
}

function renderWithLocation(initialEntries: string[] = ["/coes"]) {
  return renderHook(
    () => ({
      filters: useCoesFilters(),
      location: useLocation(),
    }),
    { wrapper: makeWrapper(initialEntries) },
  );
}

describe("useCoesFilters — initial parsing", () => {
  it("returns empty defaults when URL has no params", () => {
    const { result } = renderWithLocation(["/coes"]);
    const f = result.current.filters;
    expect(f.search).toBe("");
    expect(f.taxpayerId).toBeUndefined();
    expect(f.estadoCiclo).toBe("");
    expect(f.fechaDesde).toBe("");
    expect(f.fechaHasta).toBe("");
    expect(f.controlada).toBe("");
    expect(f.hasActiveFilters).toBe(false);
    expect(f.drawerFilterCount).toBe(0);
  });

  it("parses all filters from URL", () => {
    const { result } = renderWithLocation([
      "/coes?search=ABC&taxpayer_id=42&estado_ciclo=pendiente&fecha_desde=2026-01-01&fecha_hasta=2026-01-31&controlada=true&tipo_cte=F1,NL&periodo_mes=1&periodo_anio=2026",
    ]);
    const f = result.current.filters;
    expect(f.search).toBe("ABC");
    expect(f.taxpayerId).toBe(42);
    expect(f.estadoCiclo).toBe("pendiente");
    expect(f.fechaDesde).toBe("2026-01-01");
    expect(f.fechaHasta).toBe("2026-01-31");
    expect(f.controlada).toBe("true");
    expect(f.tipoCte).toEqual(["F1", "NL"]);
    expect(f.periodoMes).toBe("1");
    expect(f.periodoAnio).toBe("2026");
    // taxpayer + estado_ciclo + fecha range (periodo activo) + controlada + tipoCte = 5
    expect(f.drawerFilterCount).toBe(5);
    expect(f.hasActiveFilters).toBe(true);
  });

  it("ignores invalid tipo_cte values", () => {
    const { result } = renderWithLocation(["/coes?tipo_cte=F1,XX,nl"]);
    expect(result.current.filters.tipoCte).toEqual(["F1", "NL"]);
  });

  it("rejects out-of-range periodo values", () => {
    const { result } = renderWithLocation([
      "/coes?periodo_mes=13&periodo_anio=1999",
    ]);
    expect(result.current.filters.periodoMes).toBe("");
    expect(result.current.filters.periodoAnio).toBe("");
  });

  it("rejects non-positive or non-numeric taxpayer_id", () => {
    expect(renderWithLocation(["/coes?taxpayer_id=0"]).result.current.filters.taxpayerId).toBeUndefined();
    expect(renderWithLocation(["/coes?taxpayer_id=-5"]).result.current.filters.taxpayerId).toBeUndefined();
    expect(renderWithLocation(["/coes?taxpayer_id=abc"]).result.current.filters.taxpayerId).toBeUndefined();
  });

  it("coerces invalid controlada to empty", () => {
    const { result } = renderWithLocation(["/coes?controlada=maybe"]);
    expect(result.current.filters.controlada).toBe("");
  });
});

describe("useCoesFilters — setters write URL and reset page", () => {
  it("setSearch updates URL and clears page", () => {
    const { result } = renderWithLocation(["/coes?page=3"]);
    act(() => {
      result.current.filters.setSearch("hello");
    });
    expect(result.current.location.search).toContain("search=hello");
    expect(result.current.location.search).not.toContain("page=");
  });

  it("setSearch with empty string removes the param", () => {
    const { result } = renderWithLocation(["/coes?search=abc"]);
    act(() => {
      result.current.filters.setSearch("");
    });
    expect(result.current.location.search).not.toContain("search=");
  });

  it("setTaxpayerId with undefined removes the param", () => {
    const { result } = renderWithLocation(["/coes?taxpayer_id=7"]);
    act(() => {
      result.current.filters.setTaxpayerId(undefined);
    });
    expect(result.current.location.search).not.toContain("taxpayer_id");
  });

  it("setFechaDesde clears fecha_hasta when desde > hasta", () => {
    const { result } = renderWithLocation(["/coes?fecha_hasta=2026-01-10"]);
    act(() => {
      result.current.filters.setFechaDesde("2026-02-01");
    });
    expect(result.current.location.search).toContain("fecha_desde=2026-02-01");
    expect(result.current.location.search).not.toContain("fecha_hasta");
  });

  it("setFechaDesde keeps fecha_hasta when desde <= hasta", () => {
    const { result } = renderWithLocation(["/coes?fecha_hasta=2026-12-31"]);
    act(() => {
      result.current.filters.setFechaDesde("2026-01-01");
    });
    expect(result.current.location.search).toContain("fecha_desde=2026-01-01");
    expect(result.current.location.search).toContain("fecha_hasta=2026-12-31");
  });
});

describe("useCoesFilters — clearAll", () => {
  it("removes only filter params and page, preserves unrelated params", () => {
    const { result } = renderWithLocation([
      "/coes?search=x&taxpayer_id=1&estado_ciclo=pendiente&fecha_desde=2026-01-01&fecha_hasta=2026-02-01&controlada=true&tipo_cte=F1&periodo_mes=1&periodo_anio=2026&page=4&other=keep",
    ]);
    act(() => {
      result.current.filters.clearAll();
    });
    const qs = result.current.location.search;
    expect(qs).not.toContain("search=");
    expect(qs).not.toContain("taxpayer_id");
    expect(qs).not.toContain("estado_ciclo");
    expect(qs).not.toContain("fecha_desde");
    expect(qs).not.toContain("fecha_hasta");
    expect(qs).not.toContain("controlada");
    expect(qs).not.toContain("tipo_cte");
    expect(qs).not.toContain("periodo_mes");
    expect(qs).not.toContain("periodo_anio");
    expect(qs).not.toContain("page");
    expect(qs).toContain("other=keep");
  });
});

describe("useCoesFilters — tipoCte", () => {
  it("toggleTipoCte adds and removes values", () => {
    const { result } = renderWithLocation(["/coes"]);
    act(() => result.current.filters.toggleTipoCte("F1"));
    expect(result.current.location.search).toContain("tipo_cte=F1");
    act(() => result.current.filters.toggleTipoCte("NL"));
    // Order is normalized to F1,F2,NL
    expect(decodeURIComponent(result.current.location.search)).toContain("tipo_cte=F1,NL");
    act(() => result.current.filters.toggleTipoCte("F1"));
    expect(result.current.location.search).toContain("tipo_cte=NL");
    act(() => result.current.filters.toggleTipoCte("NL"));
    expect(result.current.location.search).not.toContain("tipo_cte");
  });

  it("setTipoCte normalizes order", () => {
    const { result } = renderWithLocation(["/coes"]);
    act(() => result.current.filters.setTipoCte(["NL", "F1", "F2"]));
    expect(decodeURIComponent(result.current.location.search)).toContain("tipo_cte=F1,F2,NL");
  });
});

describe("useCoesFilters — periodo", () => {
  it("setPeriodo writes fecha_desde and fecha_hasta to month bounds", () => {
    const { result } = renderWithLocation(["/coes"]);
    act(() => result.current.filters.setPeriodo("2", "2026"));
    const qs = decodeURIComponent(result.current.location.search);
    expect(qs).toContain("periodo_mes=2");
    expect(qs).toContain("periodo_anio=2026");
    expect(qs).toContain("fecha_desde=2026-02-01");
    expect(qs).toContain("fecha_hasta=2026-02-28");
  });

  it("setPeriodo handles December (31 days)", () => {
    const { result } = renderWithLocation(["/coes"]);
    act(() => result.current.filters.setPeriodo("12", "2025"));
    const qs = decodeURIComponent(result.current.location.search);
    expect(qs).toContain("fecha_desde=2025-12-01");
    expect(qs).toContain("fecha_hasta=2025-12-31");
  });

  it("setPeriodo keeps partial selection (only mes) without dropping it", () => {
    const { result } = renderWithLocation(["/coes"]);
    act(() => result.current.filters.setPeriodo("5", ""));
    const qs = result.current.location.search;
    expect(qs).toContain("periodo_mes=5");
    expect(qs).not.toContain("periodo_anio");
    expect(qs).not.toContain("fecha_desde");
    expect(qs).not.toContain("fecha_hasta");
  });

  it("setPeriodo keeps partial selection (only anio) without dropping it", () => {
    const { result } = renderWithLocation(["/coes"]);
    act(() => result.current.filters.setPeriodo("", "2026"));
    const qs = result.current.location.search;
    expect(qs).toContain("periodo_anio=2026");
    expect(qs).not.toContain("periodo_mes");
    expect(qs).not.toContain("fecha_desde");
  });

  it("setPeriodo derives fechas only once both are valid (mes first, then anio)", () => {
    const { result } = renderWithLocation(["/coes"]);
    act(() => result.current.filters.setPeriodo("5", ""));
    expect(result.current.location.search).toContain("periodo_mes=5");
    act(() =>
      result.current.filters.setPeriodo(result.current.filters.periodoMes, "2026"),
    );
    const qs = decodeURIComponent(result.current.location.search);
    expect(qs).toContain("periodo_mes=5");
    expect(qs).toContain("periodo_anio=2026");
    expect(qs).toContain("fecha_desde=2026-05-01");
    expect(qs).toContain("fecha_hasta=2026-05-31");
  });

  it("setPeriodo clearing mes preserves anio and removes derived fechas", () => {
    const { result } = renderWithLocation([
      "/coes?periodo_mes=1&periodo_anio=2026&fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
    ]);
    act(() => result.current.filters.setPeriodo("", "2026"));
    const qs = result.current.location.search;
    expect(qs).toContain("periodo_anio=2026");
    expect(qs).not.toContain("periodo_mes");
    expect(qs).not.toContain("fecha_desde");
    expect(qs).not.toContain("fecha_hasta");
  });

  it("editing fechaDesde manually clears periodo", () => {
    const { result } = renderWithLocation([
      "/coes?periodo_mes=1&periodo_anio=2026&fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
    ]);
    act(() => result.current.filters.setFechaDesde("2026-01-15"));
    const qs = result.current.location.search;
    expect(qs).toContain("fecha_desde=2026-01-15");
    expect(qs).not.toContain("periodo_mes");
    expect(qs).not.toContain("periodo_anio");
  });

  it("editing fechaHasta manually clears periodo", () => {
    const { result } = renderWithLocation([
      "/coes?periodo_mes=1&periodo_anio=2026&fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
    ]);
    act(() => result.current.filters.setFechaHasta("2026-01-20"));
    const qs = result.current.location.search;
    expect(qs).toContain("fecha_hasta=2026-01-20");
    expect(qs).not.toContain("periodo_mes");
  });
});

describe("useCoesFilters — derived flags", () => {
  it("hasActiveFilters is true with only search", () => {
    const { result } = renderWithLocation(["/coes?search=abc"]);
    expect(result.current.filters.hasActiveFilters).toBe(true);
    expect(result.current.filters.drawerFilterCount).toBe(0);
  });

  it("drawerFilterCount counts fecha range as 1, not 2", () => {
    const { result } = renderWithLocation([
      "/coes?fecha_desde=2026-01-01&fecha_hasta=2026-02-01",
    ]);
    expect(result.current.filters.drawerFilterCount).toBe(1);
  });

  it("drawerFilterCount counts only fecha_desde as 1", () => {
    const { result } = renderWithLocation(["/coes?fecha_desde=2026-01-01"]);
    expect(result.current.filters.drawerFilterCount).toBe(1);
  });

  it("drawerFilterCount counts tipo_cte as 1 regardless of how many tipos", () => {
    const { result } = renderWithLocation(["/coes?tipo_cte=F1,F2,NL"]);
    expect(result.current.filters.drawerFilterCount).toBe(1);
  });

  it("drawerFilterCount counts periodo + derived fechas as a single bucket", () => {
    const { result } = renderWithLocation([
      "/coes?periodo_mes=3&periodo_anio=2026&fecha_desde=2026-03-01&fecha_hasta=2026-03-31",
    ]);
    expect(result.current.filters.drawerFilterCount).toBe(1);
  });
});
