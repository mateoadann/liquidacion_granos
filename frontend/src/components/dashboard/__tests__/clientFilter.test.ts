import { describe, it, expect } from "vitest";
import { matchesClientQuery, normalizeClientQuery } from "../clientFilter";

const sample = {
  empresa: "MANASSERO HNOS SRL",
  cuit: "20279638612",
  cuitRepresentado: "30710910193",
};

describe("normalizeClientQuery", () => {
  it("lowercases and trims", () => {
    expect(normalizeClientQuery("  Garcia  ")).toBe("garcia");
  });

  it("returns empty string for whitespace-only input", () => {
    expect(normalizeClientQuery("   ")).toBe("");
  });
});

describe("matchesClientQuery", () => {
  it("returns true on empty query (no filter)", () => {
    expect(matchesClientQuery(sample, "")).toBe(true);
  });

  it("matches empresa case-insensitively", () => {
    expect(matchesClientQuery(sample, "manassero")).toBe(true);
    expect(matchesClientQuery(sample, "hnos")).toBe(true);
  });

  it("matches partial cuit", () => {
    expect(matchesClientQuery(sample, "20279")).toBe(true);
    expect(matchesClientQuery(sample, "612")).toBe(true);
  });

  it("matches cuit_representado", () => {
    expect(matchesClientQuery(sample, "30710")).toBe(true);
  });

  it("does not match unrelated text", () => {
    expect(matchesClientQuery(sample, "garcia")).toBe(false);
    expect(matchesClientQuery(sample, "999999999")).toBe(false);
  });

  it("query should be normalized already by caller", () => {
    // matchesClientQuery espera el query normalizado (lowercase, trim).
    // Un query con mayúsculas no matchea contra el campo empresa lowercased.
    expect(matchesClientQuery(sample, "MANASSERO")).toBe(false);
  });
});
