from __future__ import annotations

import pytest

from app.integrations.playwright.lpg_consulta_client import (
    _normalize_company_key,
    _normalize_key,
)


@pytest.mark.parametrize(
    "lhs,rhs",
    [
        ("El Socorro SRL", "EL SOCORRO S R L"),
        ("El Socorro SRL", "El Socorro S.R.L."),
        ("El Socorro SRL", "el socorro s.r.l"),
        ("Toro Cue SA", "TORO CUE S.A."),
        ("Toro Cue SA", "Toro Cue S A"),
        ("Empresa Ejemplo SAS", "EMPRESA EJEMPLO S.A.S."),
        ("Empresa Ejemplo SAS", "Empresa Ejemplo S A S"),
        ("Algo SCA", "ALGO S C A"),
        ("Algo SCA", "Algo S.C.A."),
    ],
    ids=[
        "srl-spaced-letters",
        "srl-with-dots",
        "srl-lowercase-with-dots",
        "sa-with-dots-upper",
        "sa-spaced-letters",
        "sas-with-dots-upper",
        "sas-spaced-letters",
        "sca-spaced-letters-upper",
        "sca-with-dots",
    ],
)
def test_normalize_company_key_collapses_society_suffix(lhs: str, rhs: str) -> None:
    assert _normalize_company_key(lhs) == _normalize_company_key(rhs)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Juan A Perez", "juan a perez"),
        ("", ""),
        (None, ""),
        ("Empresa Sin Forma", "empresa sin forma"),
    ],
    ids=[
        "middle-initial-not-collapsed",
        "empty-string",
        "none-value",
        "no-trailing-single-letters",
    ],
)
def test_normalize_company_key_does_not_collapse(value: str | None, expected: str) -> None:
    assert _normalize_company_key(value) == expected


def test_normalize_key_unchanged_for_compact_form() -> None:
    assert _normalize_key("El Socorro SRL") == "el socorro srl"


def test_normalize_key_unchanged_for_spaced_form() -> None:
    assert _normalize_key("EL SOCORRO S R L") == "el socorro s r l"
