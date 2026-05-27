import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useClientsFilters } from "../useClientsFilters";

function makeWrapper(initialEntries: string[] = ["/clientes"]) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>;
  };
}

function renderWithLocation(initialEntries: string[] = ["/clientes"]) {
  return renderHook(
    () => ({
      filters: useClientsFilters(),
      location: useLocation(),
    }),
    { wrapper: makeWrapper(initialEntries) },
  );
}

describe("useClientsFilters — initial parsing", () => {
  it("returns empty defaults when URL has no params", () => {
    const { result } = renderWithLocation(["/clientes"]);
    const f = result.current.filters;
    expect(f.search).toBe("");
    expect(f.active).toBe("");
    expect(f.hasCertificates).toBe("");
    expect(f.orderBy).toBe("id");
    expect(f.hasActiveFilters).toBe(false);
    expect(f.drawerFilterCount).toBe(0);
  });

  it("parses all filters from URL", () => {
    const { result } = renderWithLocation([
      "/clientes?search=garcia&active=true&has_certificates=false&order_by=empresa",
    ]);
    const f = result.current.filters;
    expect(f.search).toBe("garcia");
    expect(f.active).toBe("true");
    expect(f.hasCertificates).toBe("false");
    expect(f.orderBy).toBe("empresa");
    expect(f.drawerFilterCount).toBe(3);
    expect(f.hasActiveFilters).toBe(true);
  });

  it("coerces invalid active and has_certificates to empty", () => {
    const { result } = renderWithLocation([
      "/clientes?active=maybe&has_certificates=tal-vez",
    ]);
    expect(result.current.filters.active).toBe("");
    expect(result.current.filters.hasCertificates).toBe("");
  });

  it("coerces unknown order_by to default id", () => {
    const { result } = renderWithLocation(["/clientes?order_by=created_at"]);
    expect(result.current.filters.orderBy).toBe("id");
  });
});

describe("useClientsFilters — setters write URL and reset page", () => {
  it("setSearch updates URL and clears page", () => {
    const { result } = renderWithLocation(["/clientes?page=3"]);
    act(() => {
      result.current.filters.setSearch("manassero");
    });
    expect(result.current.location.search).toContain("search=manassero");
    expect(result.current.location.search).not.toContain("page=");
  });

  it("setOrderBy=id removes the param (default)", () => {
    const { result } = renderWithLocation(["/clientes?order_by=empresa"]);
    act(() => {
      result.current.filters.setOrderBy("id");
    });
    expect(result.current.location.search).not.toContain("order_by");
  });

  it("setActive empty string removes the param", () => {
    const { result } = renderWithLocation(["/clientes?active=true"]);
    act(() => {
      result.current.filters.setActive("");
    });
    expect(result.current.location.search).not.toContain("active");
  });
});

describe("useClientsFilters — clearAll", () => {
  it("removes only filter params and page, preserves unrelated params", () => {
    const { result } = renderWithLocation([
      "/clientes?search=x&active=true&has_certificates=false&order_by=empresa&page=4&other=keep",
    ]);
    act(() => {
      result.current.filters.clearAll();
    });
    const qs = result.current.location.search;
    expect(qs).not.toContain("search=");
    expect(qs).not.toContain("active");
    expect(qs).not.toContain("has_certificates");
    expect(qs).not.toContain("order_by");
    expect(qs).not.toContain("page");
    expect(qs).toContain("other=keep");
  });
});

describe("useClientsFilters — derived flags", () => {
  it("hasActiveFilters is true with only search", () => {
    const { result } = renderWithLocation(["/clientes?search=abc"]);
    expect(result.current.filters.hasActiveFilters).toBe(true);
    expect(result.current.filters.drawerFilterCount).toBe(0);
  });

  it("drawerFilterCount excludes search (only drawer-controlled filters)", () => {
    const { result } = renderWithLocation([
      "/clientes?search=abc&active=true&has_certificates=true",
    ]);
    expect(result.current.filters.drawerFilterCount).toBe(2);
  });

  it("orderBy=empresa increments drawerFilterCount, orderBy=id does not", () => {
    const empresa = renderWithLocation(["/clientes?order_by=empresa"]).result.current
      .filters.drawerFilterCount;
    const id = renderWithLocation(["/clientes"]).result.current.filters
      .drawerFilterCount;
    expect(empresa).toBe(1);
    expect(id).toBe(0);
  });
});
