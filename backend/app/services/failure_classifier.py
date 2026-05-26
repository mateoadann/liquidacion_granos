"""Classifies extraction job failures as retryable or not.

Used by:
- The worker auto-retry logic for scheduler-originated jobs (1 attempt max).
- The manual retry endpoint to gate the UI button on the drawer.

The classification is intentionally conservative: only transient/infra-style
failures qualify as retryable. Configuration errors (auth, expired cert) will
not get auto-retried because retrying them just wastes a slot.

Reference values come from:
- failure_phase: ExtractionPhase enum values in app.services.extraction_phases
  (LOGIN_START, SEARCH_SERVICE, OPEN_SERVICE, SELECT_EMPRESA,
   OPEN_CONSULTA_RECIBIDAS, LISTING_COES, DOWNLOADING_COE, SAVING_TO_WS, etc.)
- failure_error_type: strings produced by the Playwright pipeline
  ("auth_failed", "timeout", "network", "arca_unavailable", "unknown", ...)
"""
from __future__ import annotations

# Error types that point to a permanent config issue. A retry won't help.
NON_RETRYABLE_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "auth_failed",  # bad clave fiscal — same key will fail again
    }
)

# Error types that are typically transient: timeouts, network blips, unknown
# Playwright DOM flakes that a fresh browser may not reproduce.
RETRYABLE_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "timeout",
        "network",
        "arca_unavailable",
        "unknown",
    }
)


def is_failure_retryable(
    *, failure_phase: str | None, failure_error_type: str | None = None
) -> bool:
    """Returns True if a failed job should be eligible for retry.

    Decision is driven primarily by `failure_error_type`:
    - "auth_failed" → never retry. The credentials are wrong; a retry will
      lock the account or just fail again.
    - "timeout" / "network" / "arca_unavailable" / "unknown" → retry.

    When `failure_error_type` is missing (the worker only persisted the phase),
    we default to TREATING AS RETRYABLE. Rationale: the vast majority of
    Playwright pipeline failures are transient infra issues (ARCA latency,
    DOM flakes) and giving them one retry is cheap. If a specific
    non-transient case appears, add it explicitly to NON_RETRYABLE_ERROR_TYPES.
    """
    if failure_error_type in NON_RETRYABLE_ERROR_TYPES:
        return False
    if failure_error_type in RETRYABLE_ERROR_TYPES:
        return True
    # No granular info: default to retryable. The retry budget (max 1 for
    # auto-retry) prevents infinite loops anyway.
    return True
