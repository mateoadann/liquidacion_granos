from __future__ import annotations

from app.services.failure_classifier import is_failure_retryable


class TestIsFailureRetryable:
    def test_auth_failed_is_never_retryable(self):
        assert not is_failure_retryable(
            failure_phase="LOGIN_START", failure_error_type="auth_failed"
        )

    def test_timeout_is_retryable(self):
        assert is_failure_retryable(
            failure_phase="LISTING_COES", failure_error_type="timeout"
        )

    def test_network_is_retryable(self):
        assert is_failure_retryable(
            failure_phase=None, failure_error_type="network"
        )

    def test_arca_unavailable_is_retryable(self):
        assert is_failure_retryable(
            failure_phase="OPEN_SERVICE", failure_error_type="arca_unavailable"
        )

    def test_unknown_is_retryable(self):
        assert is_failure_retryable(
            failure_phase="SEARCH_SERVICE", failure_error_type="unknown"
        )

    def test_no_info_is_retryable_treated_as_dom_flake(self):
        """Cuando no hay ni fase ni error_type (excepción cruda) lo tratamos como
        DOM flake y conviene reintentar una vez."""
        assert is_failure_retryable(failure_phase=None, failure_error_type=None)

    def test_unrecognized_error_type_defaults_to_retryable(self):
        """Si el error_type no está catalogado pero NO es auth_failed,
        defaulteamos a retryable (la mayoría de errores son transientes)."""
        assert is_failure_retryable(
            failure_phase="LOGIN_START", failure_error_type="something_weird"
        )

    def test_auth_failed_overrides_unknown_phase(self):
        """auth_failed siempre gana, sin importar la phase."""
        assert not is_failure_retryable(
            failure_phase=None, failure_error_type="auth_failed"
        )
