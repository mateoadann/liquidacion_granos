import { describe, it, expect } from "vitest";
import { isJobRetryableInUI } from "../useJobs";
import type { Job } from "../../api/jobs";

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 1,
    taxpayer_id: 100,
    operation: "playwright_lpg_run",
    status: "failed",
    payload: {},
    result: null,
    error_message: null,
    coe_count: 0,
    created_at: "2026-05-27T12:00:00",
    started_at: null,
    finished_at: null,
    current_phase: null,
    current_message: null,
    failure_phase: null,
    failure_message_user: null,
    failure_message_technical: null,
    failure_error_type: null,
    ...overrides,
  };
}

describe("isJobRetryableInUI — non-failed statuses", () => {
  it.each(["pending", "running", "completed", "partial"] as const)(
    "returns false for status '%s'",
    (status) => {
      expect(isJobRetryableInUI(makeJob({ status }))).toBe(false);
    },
  );
});

describe("isJobRetryableInUI — error type classification", () => {
  it("returns false for auth_failed", () => {
    expect(
      isJobRetryableInUI(
        makeJob({ failure_phase: "LOGIN_START", failure_error_type: "auth_failed" }),
      ),
    ).toBe(false);
  });

  it.each(["timeout", "network", "arca_unavailable", "unknown"] as const)(
    "returns true for retryable error '%s'",
    (errorType) => {
      expect(
        isJobRetryableInUI(
          makeJob({ failure_phase: "SEARCH_SERVICE", failure_error_type: errorType }),
        ),
      ).toBe(true);
    },
  );
});

describe("isJobRetryableInUI — historical jobs without error_type", () => {
  it("returns true when failure_error_type is null and phase exists (bug case)", () => {
    // Caso original del usuario: job fallido pre-fix donde phase está set
    // pero failure_error_type quedó NULL. La versión anterior devolvía false
    // y el botón Reintentar no se mostraba; ahora default permisivo.
    expect(
      isJobRetryableInUI(
        makeJob({ failure_phase: "LOGIN_START", failure_error_type: null }),
      ),
    ).toBe(true);
  });

  it("returns true when both failure_phase and failure_error_type are null", () => {
    expect(isJobRetryableInUI(makeJob())).toBe(true);
  });

  it("returns true for unknown error_type strings", () => {
    expect(
      isJobRetryableInUI(
        makeJob({ failure_error_type: "something_new_we_havent_seen" }),
      ),
    ).toBe(true);
  });
});
