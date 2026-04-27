from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

from ..extensions import db
from ..models.coe_estado import CoeEstado
from ..models.lpg_document import LpgDocument
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class TransicionInvalidaError(Exception):
    def __init__(self, coe: str, estado_actual: str, estado_nuevo: str):
        self.coe = coe
        self.estado_actual = estado_actual
        self.estado_nuevo = estado_nuevo
        super().__init__(
            f"Transición inválida: {estado_actual} → {estado_nuevo} para COE {coe}"
        )


class HashMismatchError(Exception):
    def __init__(self, coe: str, hash_emitido: str, hash_recibido: str):
        self.coe = coe
        self.hash_emitido = hash_emitido
        self.hash_recibido = hash_recibido
        super().__init__(f"Hash mismatch para COE {coe}")


# ---------------------------------------------------------------------------
# Transiciones válidas
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pendiente": {"descargado"},
    "descargado": {"cargado", "error"},
    "error": {"cargado", "descargado"},
    "cargado": {"cargado"},  # idempotent
}


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------

CAMPOS_EXCLUIDOS_HASH = {"estado_origen", "id_liquidacion"}


def calcular_hash(liquidacion: dict) -> str:
    """Calcula hash SHA-256 del payload de liquidación, excluyendo metadatos."""
    payload = {k: v for k, v in liquidacion.items() if k not in CAMPOS_EXCLUIDOS_HASH}
    serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serializado.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validación de transición
# ---------------------------------------------------------------------------


def _validar_transicion(coe: str, estado_actual: str, estado_nuevo: str) -> None:
    destinos = VALID_TRANSITIONS.get(estado_actual, set())
    if estado_nuevo not in destinos:
        raise TransicionInvalidaError(coe, estado_actual, estado_nuevo)


# ---------------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------------


def crear_pendiente(doc: LpgDocument) -> CoeEstado | None:
    """Crea CoeEstado en estado pendiente a partir de un LpgDocument.

    Idempotente: si ya existe para el COE, retorna None sin error.
    Nunca lanza excepción — errores se loguean pero no bloquean el pipeline.
    """
    try:
        if not doc.coe:
            return None

        existing = CoeEstado.query.filter_by(coe=doc.coe).first()
        if existing:
            logger.debug("CoeEstado ya existe para COE %s, skip", doc.coe)
            return None

        datos = doc.datos_limpios or {}
        taxpayer = doc.taxpayer

        entry = CoeEstado(
            coe=doc.coe,
            lpg_document_id=doc.id,
            cuit_empresa=taxpayer.cuit_representado if taxpayer else "",
            cuit_comprador=datos.get("cuit_comprador"),
            estado="pendiente",
        )
        db.session.add(entry)
        db.session.commit()
        logger.info("CoeEstado creado | coe=%s estado=pendiente", doc.coe)
        return entry
    except Exception:
        db.session.rollback()
        logger.exception("Error creando CoeEstado para doc_id=%s", doc.id)
        return None


def marcar_descargado(
    coe: str, hash_payload: str, id_liquidacion: str
) -> CoeEstado:
    """Marca un COE como descargado con su hash y id_liquidacion."""
    entry = CoeEstado.query.filter_by(coe=coe).first()
    if not entry:
        raise ValueError(f"CoeEstado no encontrado para COE {coe}")

    _validar_transicion(coe, entry.estado, "descargado")

    entry.estado = "descargado"
    entry.descargado_en = now_cordoba_naive()
    entry.hash_payload_emitido = hash_payload
    entry.id_liquidacion = id_liquidacion
    entry.error_mensaje = None
    entry.error_fase = None
    db.session.commit()
    logger.info("CoeEstado descargado | coe=%s id_liq=%s", coe, id_liquidacion)
    return entry


def reportar_cargado(payload: dict) -> dict:
    """Procesa reporte de carga desde el liquidador externo.

    Payload esperado::

        {
            "coe": "...",
            "ejecucion_id": "...",
            "usuario": "...",
            "cargado_en": "...",
            "estado": "ok" | "error",
            "hash_payload": "sha256:...",
            "comprobante": {...},     # si estado=ok
            "error_fase": "...",      # si estado=error
            "error_mensaje": "..."    # si estado=error
        }
    """
    coe = payload["coe"]
    entry = CoeEstado.query.filter_by(coe=coe).first()
    if not entry:
        raise ValueError(f"CoeEstado no encontrado para COE {coe}")

    ejecucion_id = payload.get("ejecucion_id")
    hash_recibido = payload.get("hash_payload")
    estado_reporte = payload.get("estado")  # "ok" | "error"

    # Idempotencia: misma ejecución + hash + estado → duplicado
    estado_destino = "cargado" if estado_reporte == "ok" else "error"
    if (
        entry.ultima_ejecucion_id == ejecucion_id
        and entry.hash_payload_cargado == hash_recibido
        and entry.estado == estado_destino
    ):
        return {"duplicado": True, "coe": coe, "estado": entry.estado}

    # Si OK, verificar integridad del hash
    if estado_reporte == "ok" and hash_recibido != entry.hash_payload_emitido:
        raise HashMismatchError(coe, entry.hash_payload_emitido or "", hash_recibido or "")

    _validar_transicion(coe, entry.estado, estado_destino)

    # Actualizar campos comunes
    entry.ultima_ejecucion_id = ejecucion_id
    entry.ultimo_usuario = payload.get("usuario")
    entry.hash_payload_cargado = hash_recibido

    if estado_reporte == "ok":
        entry.estado = "cargado"
        cargado_en_str = payload.get("cargado_en")
        if cargado_en_str:
            try:
                entry.cargado_en = datetime.fromisoformat(cargado_en_str)
            except (ValueError, TypeError):
                entry.cargado_en = now_cordoba_naive()
        else:
            entry.cargado_en = now_cordoba_naive()

        comprobante = payload.get("comprobante", {})
        entry.codigo_comprobante = comprobante.get("codigo")
        entry.tipo_pto_vta = comprobante.get("tipo_pto_vta")
        entry.nro_comprobante = comprobante.get("nro")
        entry.fecha_emision = comprobante.get("fecha_emision")
        entry.error_mensaje = None
        entry.error_fase = None
    else:
        entry.estado = "error"
        entry.error_fase = payload.get("error_fase")
        entry.error_mensaje = payload.get("error_mensaje")

    db.session.commit()
    logger.info(
        "CoeEstado reportado | coe=%s estado=%s ejecucion=%s",
        coe, entry.estado, ejecucion_id,
    )
    return {
        "duplicado": False,
        "coe": coe,
        "estado": entry.estado,
        "actualizado_en": entry.actualizado_en.isoformat() if entry.actualizado_en else None,
    }


def consultar_estado(coe: str) -> dict | None:
    """Retorna el estado de un COE serializado, o None si no existe."""
    entry = CoeEstado.query.filter_by(coe=coe).first()
    if not entry:
        return None
    return _serialize_coe_estado(entry)


def listar_estados(
    cuit_empresa: str | None = None,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lista estados de COE con filtros opcionales."""
    query = CoeEstado.query

    if cuit_empresa:
        query = query.filter(CoeEstado.cuit_empresa == cuit_empresa)
    if estado:
        query = query.filter(CoeEstado.estado == estado)
    if desde:
        query = query.filter(CoeEstado.actualizado_en >= desde)
    if hasta:
        query = query.filter(CoeEstado.actualizado_en <= hasta)

    total = query.count()
    items = (
        query.order_by(CoeEstado.actualizado_en.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )

    return {
        "total": total,
        "items": [_serialize_coe_estado(e) for e in items],
    }


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------


def _serialize_coe_estado(entry: CoeEstado) -> dict:
    return {
        "id": entry.id,
        "coe": entry.coe,
        "lpg_document_id": entry.lpg_document_id,
        "cuit_empresa": entry.cuit_empresa,
        "cuit_comprador": entry.cuit_comprador,
        "codigo_comprobante": entry.codigo_comprobante,
        "tipo_pto_vta": entry.tipo_pto_vta,
        "nro_comprobante": entry.nro_comprobante,
        "fecha_emision": entry.fecha_emision,
        "id_liquidacion": entry.id_liquidacion,
        "estado": entry.estado,
        "descargado_en": entry.descargado_en.isoformat() if entry.descargado_en else None,
        "cargado_en": entry.cargado_en.isoformat() if entry.cargado_en else None,
        "error_mensaje": entry.error_mensaje,
        "error_fase": entry.error_fase,
        "ultima_ejecucion_id": entry.ultima_ejecucion_id,
        "ultimo_usuario": entry.ultimo_usuario,
        "hash_payload_emitido": entry.hash_payload_emitido,
        "hash_payload_cargado": entry.hash_payload_cargado,
        "actualizado_en": entry.actualizado_en.isoformat() if entry.actualizado_en else None,
    }
