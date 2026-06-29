from __future__ import annotations

import hashlib

# Catálogo cerrado de tipos de gestión (SPEC §2). Compartido rpa-holistor ↔ granos.
# cuenta_venta_grano: pre-carga, bloqueante (falta cuenta de venta del grano en STOCAGRO).
# carga_inconsistente: post-carga, NO bloqueante (la carga no reconcilia con Arca).
TIPOS_GESTION = (
    "alta_cliente",
    "alta_proveedor",
    "mapeo_grano",
    "alta_cuenta",
    "cuenta_venta_grano",
    "carga_inconsistente",
)


def calcular_gestion_id(tipo: str, cuit_empresa: str, identificador: str) -> str:
    """ID determinístico de una gestión. Contrato compartido rpa-holistor ↔ granos (SPEC §3).

    Normalización (CRÍTICA — ambos repos deben aplicarla idéntica):
      - tipo:          tal cual (enum snake_case en minúscula).
      - cuit_empresa:  solo dígitos (quitar '-', ' ', '.').
      - identificador: strip() + UPPER.

    El fixture tests/fixtures/gestion_id_contract.json valida esta implementación
    contra la del repo rpa-holistor.
    """
    cuit = "".join(c for c in cuit_empresa if c.isdigit())
    ident = (identificador or "").strip().upper()
    base = f"{tipo}|{cuit}|{ident}"
    return "g_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
