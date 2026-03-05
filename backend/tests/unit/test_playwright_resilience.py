from __future__ import annotations

import pytest


def test_humanized_delay_returns_value_within_range():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()
    base_ms = 1000
    variance = 0.3

    results = [client._humanized_delay(base_ms, variance) for _ in range(100)]

    min_expected = int(base_ms * (1 - variance))  # 700
    max_expected = int(base_ms * (1 + variance))  # 1300

    assert all(min_expected <= r <= max_expected for r in results)
    assert len(set(results)) > 1  # Verificar que hay variación


def test_humanized_delay_with_zero_variance_returns_base():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    result = client._humanized_delay(500, variance_percent=0.0)

    assert result == 500


def test_humanized_delay_disabled_returns_base():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    result = client._humanized_delay(500, variance_percent=0.3, enabled=False)

    assert result == 500


def test_classify_error_network_is_transient():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(Exception("net::ERR_CONNECTION_RESET"))

    assert classification.is_transient is True
    assert classification.error_type == "network"


def test_classify_error_timeout_is_transient():
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(PlaywrightTimeoutError("Timeout 30000ms"))

    assert classification.is_transient is True
    assert classification.error_type == "timeout"


def test_classify_error_auth_failed_is_not_transient():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(
        PlaywrightFlowError("clave o usuario incorrecto")
    )

    assert classification.is_transient is False
    assert classification.error_type == "auth_failed"


def test_classify_error_arca_unavailable_is_transient():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()

    classification = client._classify_error(
        PlaywrightFlowError("servicio no disponible")
    )

    assert classification.is_transient is True
    assert classification.error_type == "arca_unavailable"


def test_retry_wrapper_succeeds_first_attempt(mocker):
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()
    mock_operation = mocker.Mock(return_value="success")

    result = client._with_retry(
        operation=mock_operation,
        operation_name="test_op",
        max_attempts=2,
        base_delay_ms=100,
        empresa="TestEmpresa",
    )

    assert result == "success"
    assert mock_operation.call_count == 1


def test_retry_wrapper_succeeds_second_attempt(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()
    mock_operation = mocker.Mock(
        side_effect=[PlaywrightFlowError("servicio no disponible"), "success"]
    )
    mock_page = mocker.Mock()
    mock_page.wait_for_timeout = mocker.Mock()

    result = client._with_retry(
        operation=mock_operation,
        operation_name="test_op",
        max_attempts=2,
        base_delay_ms=100,
        empresa="TestEmpresa",
        page=mock_page,
    )

    assert result == "success"
    assert mock_operation.call_count == 2


def test_retry_wrapper_aborts_on_same_error(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()
    error = PlaywrightFlowError("servicio no disponible")
    mock_operation = mocker.Mock(side_effect=[error, error])
    mock_page = mocker.Mock()
    mock_page.wait_for_timeout = mocker.Mock()

    with pytest.raises(PlaywrightFlowError) as exc_info:
        client._with_retry(
            operation=mock_operation,
            operation_name="test_op",
            max_attempts=2,
            base_delay_ms=100,
            empresa="TestEmpresa",
            page=mock_page,
        )

    assert "servicio no disponible" in str(exc_info.value)
    assert mock_operation.call_count == 2


def test_retry_wrapper_aborts_on_non_transient_error(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )

    client = ArcaLpgPlaywrightClient()
    error = PlaywrightFlowError("clave o usuario incorrecto")
    mock_operation = mocker.Mock(side_effect=error)

    with pytest.raises(PlaywrightFlowError) as exc_info:
        client._with_retry(
            operation=mock_operation,
            operation_name="test_op",
            max_attempts=2,
            base_delay_ms=100,
            empresa="TestEmpresa",
        )

    assert "clave o usuario incorrecto" in str(exc_info.value)
    assert mock_operation.call_count == 1  # No reintenta
