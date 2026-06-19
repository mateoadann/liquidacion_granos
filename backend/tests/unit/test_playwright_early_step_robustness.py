"""Tests for P0/P1/P3 reliability improvements on the Playwright pipeline.

P0 — failure_phase is never None when an early step fails.
P1 — transient errors in early steps are retried; auth/unknown fail fast.
P3 — nav_login_timeout_ms is threaded through and used for goto calls;
     config default is 60000.

Mocking strategy (mirrors test_playwright_jobs_phase_persistence.py):
- ArcaLpgPlaywrightClient is patched on the pipeline module so we never
  touch real Playwright or AFIP.
- LpgPlaywrightPipelineService._process_taxpayer is exercised end-to-end
  through the test (no double-mocking).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from app.integrations.playwright.lpg_consulta_client import (
    ArcaLpgPlaywrightClient,
    LpgConsultaRequest,
    LpgCredentials,
    PlaywrightFlowError,
)
from app.services.extraction_phases import ExtractionPhase
from app.services.lpg_playwright_pipeline import (
    LpgPlaywrightPipelineService,
    TaxpayerPipelineResult,
)
from app.workers.scheduler_defaults import (
    DEFAULT_NAV_LOGIN_TIMEOUT_MS,
    scheduler_enqueue_kwargs,
)


# ---------------------------------------------------------------------------
# Helper — minimal LpgConsultaRequest (does not invoke Playwright)
# ---------------------------------------------------------------------------

def _make_request(**overrides: Any) -> LpgConsultaRequest:
    defaults: dict[str, Any] = dict(
        credentials=LpgCredentials(cuit="20111111111", clave_fiscal="test"),
        empresa="Test SA",
        fecha_desde="01/01/2026",
        fecha_hasta="31/01/2026",
    )
    defaults.update(overrides)
    return LpgConsultaRequest(**defaults)


# ---------------------------------------------------------------------------
# P0 — _current_phase tracking on ArcaLpgPlaywrightClient
# ---------------------------------------------------------------------------

class TestCurrentPhaseTracking:
    def test_current_phase_starts_as_none(self):
        client = ArcaLpgPlaywrightClient()
        assert client._current_phase is None

    def test_emit_phase_sets_current_phase_before_callback(self):
        recorded: list[ExtractionPhase] = []

        def cb(phase: ExtractionPhase, msg: str) -> None:
            # At the moment the callback fires, _current_phase must already
            # be updated.
            recorded.append(client._current_phase)  # type: ignore[attr-defined]

        client = ArcaLpgPlaywrightClient()
        client._on_phase = cb
        client._emit_phase(ExtractionPhase.SELECT_EMPRESA)

        assert client._current_phase is ExtractionPhase.SELECT_EMPRESA
        assert recorded == [ExtractionPhase.SELECT_EMPRESA]

    def test_emit_phase_updates_even_if_callback_raises(self):
        def bad_cb(phase: ExtractionPhase, msg: str) -> None:
            raise RuntimeError("callback boom")

        client = ArcaLpgPlaywrightClient()
        client._on_phase = bad_cb
        # Should not propagate; _current_phase should still be updated.
        client._emit_phase(ExtractionPhase.OPEN_CONSULTA_RECIBIDAS)
        assert client._current_phase is ExtractionPhase.OPEN_CONSULTA_RECIBIDAS

    def test_run_resets_current_phase_at_start(self):
        """run() resets _current_phase to None before invoking _run_with_playwright,
        so stale phase info from a previous run does not bleed across requests."""

        client = ArcaLpgPlaywrightClient()
        client._current_phase = ExtractionPhase.LISTING_COES  # leftover from hypothetical prior run

        phase_at_start: list[Any] = []

        original_rwp = client._run_with_playwright

        def capturing_rwp(playwright: Any, request: Any) -> Any:
            # _current_phase is checked at the moment _run_with_playwright is entered,
            # BEFORE any _emit_phase() call inside it.
            # We capture it, then raise to skip the real browser.
            phase_at_start.append(client._current_phase)
            raise RuntimeError("abort — no browser needed")

        client._run_with_playwright = capturing_rwp  # type: ignore[method-assign]

        with patch("app.integrations.playwright.lpg_consulta_client.sync_playwright"):
            request = _make_request()
            try:
                client.run(request)
            except RuntimeError:
                pass

        assert phase_at_start == [None], (
            f"Expected _current_phase=None at start of _run_with_playwright, got {phase_at_start}"
        )

    def test_emit_phase_no_callback_still_tracks(self):
        client = ArcaLpgPlaywrightClient()
        client._on_phase = None
        client._emit_phase(ExtractionPhase.SET_FECHAS)
        assert client._current_phase is ExtractionPhase.SET_FECHAS


# ---------------------------------------------------------------------------
# P0 — pipeline preserves failure_phase from _current_phase on generic Exception
# ---------------------------------------------------------------------------

class TestPipelineFailurePhaseFallback:
    """Verify that when the client raises a raw (non-PlaywrightFlowError)
    exception — e.g. PlaywrightTimeoutError, OSError — the pipeline sets
    failure_phase to the last emitted phase instead of None."""

    def _make_fake_client(
        self,
        *,
        last_phase: ExtractionPhase | None,
        raises: Exception,
    ) -> MagicMock:
        """Returns a mock client whose run() raises after setting _current_phase."""
        client = MagicMock(spec=ArcaLpgPlaywrightClient)
        client._current_phase = last_phase
        client._search_dropdown_clicked = False
        client._classify_error.return_value = MagicMock(error_type="timeout")
        client.run.side_effect = raises
        return client

    def _run_process_taxpayer(
        self,
        svc: LpgPlaywrightPipelineService,
        tp: Any,
        fake_client: MagicMock,
    ) -> TaxpayerPipelineResult:
        import app.services.lpg_playwright_pipeline as pipeline_module

        # Bypass _resolve_clave_fiscal (needs real crypto) and
        # _validate_taxpayer_ws_config (needs DB WS config).
        with (
            patch.object(svc, "_resolve_clave_fiscal", return_value="dummy_clave"),
            patch.object(svc, "_validate_taxpayer_ws_config", return_value=None),
            patch.object(
                pipeline_module, "ArcaLpgPlaywrightClient", return_value=fake_client
            ),
        ):
            return svc._process_taxpayer(
                taxpayer=tp,
                fecha_desde="01/01/2026",
                fecha_hasta="31/01/2026",
                headless=True,
                timeout_ms=30000,
                type_delay_ms=80,
                slow_mo_ms=0,
                post_action_delay_ms=0,
                login_max_retries=2,
                humanize_delays=False,
                retry_max_attempts=2,
                retry_base_delay_ms=100,
            )

    def test_generic_exception_uses_current_phase(self, app):
        """Raw RuntimeError → failure_phase comes from client._current_phase."""
        from app.extensions import db
        from app.models import Taxpayer

        with app.app_context():
            tp = Taxpayer()
            tp.cuit = "20111111111"
            tp.empresa = "Test SA"
            tp.cuit_representado = "20111111111"
            tp.clave_fiscal_encrypted = "test"
            tp.playwright_enabled = True
            tp.activo = True
            db.session.add(tp)
            db.session.commit()

            last_phase = ExtractionPhase.SET_FECHAS
            fake_client = self._make_fake_client(
                last_phase=last_phase,
                raises=RuntimeError("connection reset by peer"),
            )

            result = self._run_process_taxpayer(
                LpgPlaywrightPipelineService(), tp, fake_client
            )

            assert result.outcome == "error"
            assert result.failure_phase is ExtractionPhase.SET_FECHAS, (
                f"Expected SET_FECHAS but got {result.failure_phase}"
            )

    def test_generic_exception_with_no_phase_emitted_gives_none(self, app):
        """If the client crashes before any phase is emitted, failure_phase
        is still None (the phase is genuinely unknown, not a bug)."""
        from app.extensions import db
        from app.models import Taxpayer

        with app.app_context():
            tp = Taxpayer()
            tp.cuit = "20222222222"
            tp.empresa = "Test SA2"
            tp.cuit_representado = "20222222222"
            tp.clave_fiscal_encrypted = "test"
            tp.playwright_enabled = True
            tp.activo = True
            db.session.add(tp)
            db.session.commit()

            fake_client = self._make_fake_client(
                last_phase=None,
                raises=OSError("no network"),
            )

            result = self._run_process_taxpayer(
                LpgPlaywrightPipelineService(), tp, fake_client
            )

            assert result.outcome == "error"
            assert result.failure_phase is None

    def test_playwright_flow_error_without_phase_falls_back_to_current_phase(self, app):
        """A PlaywrightFlowError(phase=None) should use client._current_phase
        rather than leaving failure_phase as None."""
        from app.extensions import db
        from app.models import Taxpayer

        with app.app_context():
            tp = Taxpayer()
            tp.cuit = "20333333333"
            tp.empresa = "Test SA3"
            tp.cuit_representado = "20333333333"
            tp.clave_fiscal_encrypted = "test"
            tp.playwright_enabled = True
            tp.activo = True
            db.session.add(tp)
            db.session.commit()

            # PlaywrightFlowError with no explicit phase, but client tracked OPEN_CONSULTA_RECIBIDAS
            error = PlaywrightFlowError("timeout filling form")
            assert error.phase is None

            fake_client = MagicMock(spec=ArcaLpgPlaywrightClient)
            fake_client._current_phase = ExtractionPhase.OPEN_CONSULTA_RECIBIDAS
            fake_client._search_dropdown_clicked = False
            fake_client._classify_error.return_value = MagicMock(error_type="timeout")
            fake_client.run.side_effect = error

            result = self._run_process_taxpayer(
                LpgPlaywrightPipelineService(), tp, fake_client
            )

            assert result.outcome == "error"
            assert result.failure_phase is ExtractionPhase.OPEN_CONSULTA_RECIBIDAS


# ---------------------------------------------------------------------------
# P1 — _with_retry wraps early steps
# ---------------------------------------------------------------------------

class TestWithRetryOnEarlySteps:
    """Tests for retry behaviour on _select_empresa, _open_consulta_recibidas,
    and _set_fechas when they raise transient (timeout) errors."""

    def _make_client_with_counted_call(
        self,
        *,
        phase_before_fail: ExtractionPhase,
        method_name: str,
        fail_times: int,
        return_value: Any = None,
        error_factory: Any = None,
    ) -> ArcaLpgPlaywrightClient:
        """Returns a real ArcaLpgPlaywrightClient with one method stubbed to
        fail `fail_times` times with a timeout error, then succeed."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        client = ArcaLpgPlaywrightClient()
        calls: list[int] = []

        def stubbed_method(*args: Any, **kwargs: Any) -> Any:
            calls.append(1)
            if len(calls) <= fail_times:
                if error_factory:
                    raise error_factory()
                raise PlaywrightTimeoutError("Timeout 30000ms exceeded")
            return return_value

        setattr(client, method_name, stubbed_method)
        client._call_count = calls  # type: ignore[attr-defined]
        return client

    def test_select_empresa_retries_on_timeout_succeeds_second_attempt(self):
        """_select_empresa wrapped in _with_retry: first call raises
        PlaywrightTimeoutError, second call succeeds."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        client = ArcaLpgPlaywrightClient()
        client._current_phase = ExtractionPhase.SELECT_EMPRESA

        call_count = 0

        def failing_select(service_page: Any, empresa: str, timeout_ms: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PlaywrightTimeoutError("Timeout 30000ms exceeded")

        client._select_empresa = failing_select  # type: ignore[method-assign]

        mock_page = MagicMock()
        mock_page.wait_for_timeout = MagicMock()

        client._with_retry(
            operation=lambda: client._select_empresa(mock_page, "Test SA", 30000),
            operation_name="select_empresa",
            max_attempts=2,
            base_delay_ms=0,
            empresa="Test SA",
            page=mock_page,
        )

        assert call_count == 2, f"Expected 2 calls, got {call_count}"

    def test_select_empresa_auth_error_fails_immediately_no_retry(self):
        """An auth error (non-transient) is NOT retried."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        client = ArcaLpgPlaywrightClient()
        call_count = 0

        def auth_fail(service_page: Any, empresa: str, timeout_ms: int) -> None:
            nonlocal call_count
            call_count += 1
            raise PlaywrightFlowError(
                "clave o usuario incorrecto", phase=ExtractionPhase.LOGIN_START
            )

        client._select_empresa = auth_fail  # type: ignore[method-assign]
        mock_page = MagicMock()
        mock_page.wait_for_timeout = MagicMock()

        with pytest.raises(PlaywrightFlowError):
            client._with_retry(
                operation=lambda: client._select_empresa(mock_page, "Test SA", 30000),
                operation_name="select_empresa",
                max_attempts=3,
                base_delay_ms=0,
                empresa="Test SA",
                page=mock_page,
            )

        # Even with max_attempts=3, auth error must not retry.
        assert call_count == 1, f"Auth error should not be retried but got {call_count} calls"

    def test_set_fechas_retries_on_timeout_then_succeeds(self):
        """_set_fechas wrapped in _with_retry retries a transient timeout."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        client = ArcaLpgPlaywrightClient()
        call_count = 0

        def failing_set_fechas(
            service_page: Any, desde: str, hasta: str, timeout_ms: int,
            empresa: str, humanize: bool = True
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PlaywrightTimeoutError("Timeout 30000ms exceeded")

        client._set_fechas = failing_set_fechas  # type: ignore[method-assign]
        mock_page = MagicMock()
        mock_page.wait_for_timeout = MagicMock()

        client._with_retry(
            operation=lambda: client._set_fechas(
                mock_page, "01/01/2026", "31/01/2026", 30000, "Test SA", False
            ),
            operation_name="set_fechas",
            max_attempts=2,
            base_delay_ms=0,
            empresa="Test SA",
            page=mock_page,
        )

        assert call_count == 2

    def test_open_consulta_recibidas_retries_on_timeout(self):
        """_open_consulta_recibidas wrapped in _with_retry retries a transient timeout."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        client = ArcaLpgPlaywrightClient()
        call_count = 0

        def failing_open(
            service_page: Any, timeout_ms: int, empresa: str, humanize: bool = True
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PlaywrightTimeoutError("Timeout 30000ms exceeded")

        client._open_consulta_recibidas = failing_open  # type: ignore[method-assign]
        mock_page = MagicMock()
        mock_page.wait_for_timeout = MagicMock()

        client._with_retry(
            operation=lambda: client._open_consulta_recibidas(
                mock_page, 30000, "Test SA", False
            ),
            operation_name="open_consulta_recibidas",
            max_attempts=2,
            base_delay_ms=0,
            empresa="Test SA",
            page=mock_page,
        )

        assert call_count == 2

    def test_unknown_error_in_set_fechas_fails_fast(self):
        """An unknown error (non-transient) from _set_fechas is not retried."""
        client = ArcaLpgPlaywrightClient()
        call_count = 0

        def unknown_fail(
            service_page: Any, desde: str, hasta: str, timeout_ms: int,
            empresa: str, humanize: bool = True
        ) -> None:
            nonlocal call_count
            call_count += 1
            # PlaywrightFlowError with a message that does not match any
            # transient pattern → classified as "unknown" → not retried.
            raise PlaywrightFlowError("unexpected DOM structure")

        client._set_fechas = unknown_fail  # type: ignore[method-assign]
        mock_page = MagicMock()
        mock_page.wait_for_timeout = MagicMock()

        with pytest.raises(PlaywrightFlowError):
            client._with_retry(
                operation=lambda: client._set_fechas(
                    mock_page, "01/01/2026", "31/01/2026", 30000, "Test SA", False
                ),
                operation_name="set_fechas",
                max_attempts=3,
                base_delay_ms=0,
                empresa="Test SA",
                page=mock_page,
            )

        # Not retried: should be called exactly once.
        assert call_count == 1


# ---------------------------------------------------------------------------
# P1 — _emit_phase SET_FECHAS is emitted before _set_fechas
# ---------------------------------------------------------------------------

class TestSetFechasPhaseEmission:
    def test_set_fechas_phase_emitted(self):
        """SET_FECHAS must be in the ExtractionPhase enum and have a message."""
        from app.services.extraction_phases import PHASE_MESSAGES_ES, ExtractionPhase

        assert hasattr(ExtractionPhase, "SET_FECHAS")
        assert ExtractionPhase.SET_FECHAS in PHASE_MESSAGES_ES
        assert PHASE_MESSAGES_ES[ExtractionPhase.SET_FECHAS]

    def test_current_phase_is_set_fechas_after_set_fechas_emitted(self):
        """_emit_phase(SET_FECHAS) sets _current_phase correctly."""
        client = ArcaLpgPlaywrightClient()
        client._emit_phase(ExtractionPhase.SET_FECHAS)
        assert client._current_phase is ExtractionPhase.SET_FECHAS


# ---------------------------------------------------------------------------
# P3 — nav_login_timeout_ms is threaded and used for goto
# ---------------------------------------------------------------------------

class TestNavLoginTimeout:
    def test_nav_login_timeout_ms_default_on_request(self):
        """LpgConsultaRequest default nav_login_timeout_ms is 60000."""
        req = _make_request()
        assert req.nav_login_timeout_ms == 60_000

    def test_nav_login_timeout_ms_custom_value_accepted(self):
        req = _make_request(nav_login_timeout_ms=90_000)
        assert req.nav_login_timeout_ms == 90_000

    def test_scheduler_defaults_include_nav_login_timeout_ms(self):
        """scheduler_enqueue_kwargs must include nav_login_timeout_ms."""
        kwargs = scheduler_enqueue_kwargs(taxpayer_id=1)
        assert "nav_login_timeout_ms" in kwargs
        assert kwargs["nav_login_timeout_ms"] == DEFAULT_NAV_LOGIN_TIMEOUT_MS

    def test_default_nav_login_timeout_ms_constant_is_60000(self):
        assert DEFAULT_NAV_LOGIN_TIMEOUT_MS == 60_000

    def test_goto_landing_receives_nav_login_timeout_ms(self):
        """_do_login_attempt must call goto with the explicit nav_login_timeout_ms."""
        client = ArcaLpgPlaywrightClient()
        request = _make_request(nav_login_timeout_ms=90_000, retry_max_attempts=1)

        # Mock the landing page
        mock_page = MagicMock()
        mock_page.wait_for_timeout = MagicMock()
        # goto returns None (success)
        mock_page.goto.return_value = None

        # We need _with_retry to actually call goto; patch expect_popup to
        # prevent the real flow from continuing.
        mock_page.expect_popup.side_effect = RuntimeError("stop here")

        with pytest.raises(RuntimeError, match="stop here"):
            client._do_login_attempt(mock_page, request)

        # goto must have been called with timeout=90000
        assert mock_page.goto.called
        goto_kwargs = mock_page.goto.call_args
        assert goto_kwargs.kwargs.get("timeout") == 90_000 or (
            len(goto_kwargs.args) >= 1 and goto_kwargs.kwargs.get("timeout") == 90_000
        ), f"goto was called with: {goto_kwargs}"

    def test_goto_lpg_direct_receives_nav_login_timeout_ms(self):
        """_open_lpg_service_via_direct_url calls goto with nav_login_timeout_ms."""
        client = ArcaLpgPlaywrightClient()

        mock_direct_page = MagicMock()
        mock_direct_page.wait_for_timeout = MagicMock()
        mock_direct_page.goto.return_value = None

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_direct_page

        mock_login_page = MagicMock()
        mock_login_page.context = mock_context

        # _wait_for_service_page_ready will fail since mock_direct_page has no
        # real content — that's fine, we just check goto was called correctly.
        with pytest.raises(Exception):
            client._open_lpg_service_via_direct_url(
                mock_login_page,
                timeout_ms=30_000,
                empresa="Test SA",
                nav_login_timeout_ms=75_000,
            )

        assert mock_direct_page.goto.called
        goto_kwargs = mock_direct_page.goto.call_args
        assert goto_kwargs.kwargs.get("timeout") == 75_000, (
            f"Expected timeout=75000, got: {goto_kwargs}"
        )

    def test_config_playwright_nav_login_timeout_ms_default(self):
        """Config default for PLAYWRIGHT_NAV_LOGIN_TIMEOUT_MS is 60000."""
        import os
        # Ensure env var is not set so we test the default.
        os.environ.pop("PLAYWRIGHT_NAV_LOGIN_TIMEOUT_MS", None)
        from app.config import Config
        assert Config.PLAYWRIGHT_NAV_LOGIN_TIMEOUT_MS == 60_000

    def test_config_playwright_timeout_ms_default(self):
        """Config default for PLAYWRIGHT_TIMEOUT_MS is 30000."""
        import os
        os.environ.pop("PLAYWRIGHT_TIMEOUT_MS", None)
        from app.config import Config
        assert Config.PLAYWRIGHT_TIMEOUT_MS == 30_000
