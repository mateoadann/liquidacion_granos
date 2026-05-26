"""Regression tests for logging_setup.

The arca_arg.webservice logger dumps the AFIP SSO token + HMAC sign in
plaintext at INFO level on every SOAP call. The token is a credential
valid for ~12h that grants access to wslpg on behalf of the represented
CUIT, so it MUST stay above INFO regardless of the global LOG_LEVEL.
"""
from __future__ import annotations

import logging

from app.logging_setup import configure_logging


def test_arca_arg_webservice_logger_silenced_with_default_info_level():
    configure_logging("INFO")
    assert logging.getLogger("arca_arg.webservice").level >= logging.WARNING


def test_arca_arg_webservice_logger_silenced_even_with_debug_level():
    """Even if the operator opts into DEBUG globally, AFIP tokens stay hidden."""
    configure_logging("DEBUG")
    assert logging.getLogger("arca_arg.webservice").level >= logging.WARNING


def test_arca_arg_webservice_logger_silenced_with_none_level():
    """No LOG_LEVEL env var falls back to INFO; the logger stays silenced."""
    configure_logging(None)
    assert logging.getLogger("arca_arg.webservice").level >= logging.WARNING
