from __future__ import annotations

ALLOWED_AMBIENTES = {"homologacion", "produccion"}


def is_valid_cuit(cuit: str | None) -> bool:
    value = str(cuit or "").strip()
    return len(value) == 11 and value.isdigit()


def is_valid_ambiente(ambiente: str | None) -> bool:
    value = str(ambiente or "").strip().lower()
    return value in ALLOWED_AMBIENTES
