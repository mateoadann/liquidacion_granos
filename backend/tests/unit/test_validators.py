from __future__ import annotations

from app.services.validators import is_valid_cuit


def test_valid_cuit_returns_true():
    assert is_valid_cuit("20304050607") is True


def test_invalid_cuit_returns_false_for_letters():
    assert is_valid_cuit("20A04050607") is False


def test_invalid_cuit_returns_false_for_short_value():
    assert is_valid_cuit("123") is False
