from __future__ import annotations

import pytest

from app.api.jobs import _extract_coe_count


# ---------------------------------------------------------------------------
# New-style jobs: key "total_coes_nuevos" is present
# ---------------------------------------------------------------------------

def test_new_job_uses_total_coes_nuevos(app):
    """When total_coes_nuevos is present, use it — even if detectados is larger."""
    result = {
        "results": [
            {"total_coes_nuevos": 3, "total_coes_detectados": 10},
        ]
    }
    assert _extract_coe_count(result) == 3


def test_new_job_zero_nuevos_does_not_fall_back(app):
    """Key present with 0 → must return 0, NOT fall back to total_coes_detectados."""
    result = {
        "results": [
            {"total_coes_nuevos": 0, "total_coes_detectados": 5},
        ]
    }
    assert _extract_coe_count(result) == 0


# ---------------------------------------------------------------------------
# Old-style jobs: key "total_coes_nuevos" is absent → fallback
# ---------------------------------------------------------------------------

def test_old_job_falls_back_to_detectados(app):
    """Job without total_coes_nuevos key uses total_coes_detectados as fallback."""
    result = {
        "results": [
            {"total_coes_detectados": 7},
        ]
    }
    assert _extract_coe_count(result) == 7


# ---------------------------------------------------------------------------
# Multi-element results list
# ---------------------------------------------------------------------------

def test_multiple_results_sums_correctly(app):
    """Mixed new-style and old-style entries sum independently."""
    result = {
        "results": [
            {"total_coes_nuevos": 3, "total_coes_detectados": 10},  # new-style → 3
            {"total_coes_nuevos": 0, "total_coes_detectados": 5},   # new-style zero → 0
            {"total_coes_detectados": 7},                            # old-style → 7
            {"total_coes_nuevos": 2},                                # new-style, no detectados → 2
        ]
    }
    assert _extract_coe_count(result) == 12


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_none_result_returns_zero(app):
    assert _extract_coe_count(None) == 0


def test_empty_dict_returns_zero(app):
    assert _extract_coe_count({}) == 0


def test_empty_results_list_returns_zero(app):
    assert _extract_coe_count({"results": []}) == 0


def test_non_dict_result_returns_zero(app):
    assert _extract_coe_count("not-a-dict") == 0  # type: ignore[arg-type]


def test_non_dict_entries_in_results_are_skipped(app):
    """Corrupt entries (None, int) inside results must not raise — they are skipped."""
    result = {
        "results": [
            None,
            42,
            {"total_coes_nuevos": 4, "total_coes_detectados": 9},
        ]
    }
    assert _extract_coe_count(result) == 4
