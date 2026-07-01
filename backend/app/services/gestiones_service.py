from __future__ import annotations

from ..extensions import db
from ..models.gestion import Gestion
from ..models.lpg_document import LpgDocument
from ..time_utils import now_cordoba_naive
from .gestion_id import TIPOS_GESTION


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class TransicionInvalidaError(Exception):
    def __init__(self, gestion_id: str, estado_actual: str, estado_nuevo: str):
        self.gestion_id = gestion_id
        self.estado_actual = estado_actual
        self.estado_nuevo = estado_nuevo
        super().__init__(
            f"Transición inválida: {estado_actual} → {estado_nuevo} para {gestion_id}"
        )


class GestionNoEncontradaError(Exception):
    def __init__(self, gestion_id: str):
        self.gestion_id = gestion_id
        super().__init__(f"Gestión {gestion_id} no existe.")


class ValidacionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Máquina de estados (SPEC §8.2)
# ---------------------------------------------------------------------------

ESTADOS = ("pendiente", "realizada", "verificada", "verificacion_fallida")


def _serialize(g: Gestion) -> dict:
    return {
        "gestion_id": g.gestion_id,
        "tipo": g.tipo,
        "cuit_empresa": g.cuit_empresa,
        "razon_social": g.razon_social,
        "identificador": g.identificador,
        "descripcion": g.descripcion,
        "datos_contexto": g.datos_contexto,
        "coes_afectados": g.coes_afectados or [],
        "estado": g.estado,
        "detectado_en": g.detectado_en,
        "realizada_en": g.realizada_en,
        "realizada_por": g.realizada_por,
        "verificada_en": g.verificada_en,
        "verificacion_detalle": g.verificacion_detalle,
    }


# ---------------------------------------------------------------------------
# POST /v1/gestiones — crear/refrescar batch (SPEC §8.3)
# ---------------------------------------------------------------------------

CAMPOS_REQUERIDOS = ("gestion_id", "tipo", "cuit_empresa", "identificador", "descripcion", "detectado_en")


def crear_o_refrescar_batch(gestiones: list[dict]) -> dict:
    """Idempotente por gestion_id (SPEC §6, §8.3).

    - gestion_id nuevo → INSERT estado='pendiente'. Cuenta como 'creada'.
    - gestion_id existente → UPDATE de metadata mutable; NO toca estado. Cuenta como 'actualizada'.

    Valida cada gestión; si alguna es inválida levanta ValidacionError (rechaza el batch).
    """
    for item in gestiones:
        faltantes = [c for c in CAMPOS_REQUERIDOS if not item.get(c)]
        if faltantes:
            raise ValidacionError(f"Campos requeridos faltantes: {', '.join(faltantes)}")
        if item["tipo"] not in TIPOS_GESTION:
            raise ValidacionError(f"tipo inválido: {item['tipo']}. Permitidos: {', '.join(TIPOS_GESTION)}")

    # Dedup intra-batch por gestion_id: si el mismo faltante llega dos veces en
    # un lote (varios COEs apuntan a una gestión, antes de la dedup de RPA),
    # nos quedamos con la última ocurrencia (foto más fresca de coes_afectados,
    # §6). Sin esto, dos INSERT del mismo PK revientan el commit entero.
    dedup: dict[str, dict] = {}
    for item in gestiones:
        dedup[item["gestion_id"]] = item
    items = list(dedup.values())

    resultados = []
    creadas = 0
    actualizadas = 0

    for item in items:
        gid = item["gestion_id"]
        existente = db.session.get(Gestion, gid)
        if existente is None:
            g = Gestion()
            g.gestion_id = gid
            g.tipo = item["tipo"]
            g.cuit_empresa = item["cuit_empresa"]
            g.razon_social = item.get("razon_social")
            g.identificador = item["identificador"]
            g.descripcion = item["descripcion"]
            g.datos_contexto = item.get("datos_contexto")
            g.coes_afectados = item.get("coes_afectados") or []
            g.estado = "pendiente"
            g.detectado_en = item["detectado_en"]
            db.session.add(g)
            creadas += 1
            resultados.append({"gestion_id": gid, "accion": "creada", "duplicado": False})
        else:
            # Refresca metadata mutable; NO toca estado (idempotente).
            existente.descripcion = item["descripcion"]
            existente.datos_contexto = item.get("datos_contexto")
            existente.coes_afectados = item.get("coes_afectados") or []
            if item.get("razon_social"):
                existente.razon_social = item["razon_social"]
            if not existente.detectado_en:
                existente.detectado_en = item["detectado_en"]
            actualizadas += 1
            resultados.append({"gestion_id": gid, "accion": "actualizada", "duplicado": True})

    db.session.commit()

    return {
        "recibidas": len(items),  # tras dedup intra-batch; invariante: creadas+actualizadas
        "creadas": creadas,
        "actualizadas": actualizadas,
        "resultados": resultados,
    }


# ---------------------------------------------------------------------------
# GET /v1/gestiones — listar (SPEC §8.4)
# ---------------------------------------------------------------------------


def listar(estados: list[str] | None = None, cuits_empresa: list[str] | None = None, desde: str | None = None) -> dict:
    query = Gestion.query
    if estados:
        query = query.filter(Gestion.estado.in_(estados))
    if cuits_empresa:
        query = query.filter(Gestion.cuit_empresa.in_(cuits_empresa))
    if desde:
        query = query.filter(Gestion.detectado_en >= desde)
    query = query.order_by(Gestion.detectado_en.asc())
    gestiones = query.all()
    return {"total": len(gestiones), "gestiones": [_serialize(g) for g in gestiones]}


# ---------------------------------------------------------------------------
# POST /v1/gestiones/{id}/verificacion — RPA confirma (SPEC §8.5)
# ---------------------------------------------------------------------------


def confirmar_verificacion(gestion_id: str, resultado: str, detalle: str | None = None, verificado_en: str | None = None) -> dict:
    """realizada → verificada | verificacion_fallida (SPEC §8.5).

    Válido desde 'realizada'. Idempotente: si la gestión ya está en el estado
    pedido, devuelve 200 no-op (no 409) — cubre el re-confirm pass del RPA
    cuando el ACK de un confirm previo se perdió por corte de red y reintenta
    sobre una gestión ya verificada/fallida del lado granos.
    Desde cualquier otro estado → TransicionInvalidaError.
    """
    if resultado not in ("verificada", "verificacion_fallida"):
        raise ValidacionError("resultado debe ser 'verificada' o 'verificacion_fallida'.")

    g = db.session.get(Gestion, gestion_id)
    if g is None:
        raise GestionNoEncontradaError(gestion_id)

    # Idempotencia del re-confirm: mismo estado pedido → no-op.
    if g.estado == resultado:
        return {"gestion_id": g.gestion_id, "estado": g.estado}

    if g.estado != "realizada":
        raise TransicionInvalidaError(gestion_id, g.estado, resultado)

    g.estado = resultado
    g.verificacion_detalle = detalle
    if resultado == "verificada":
        g.verificada_en = verificado_en or now_cordoba_naive().isoformat()
        _limpiar_control_rpa_afectados(g)
    db.session.commit()

    return {"gestion_id": g.gestion_id, "estado": g.estado}


def _limpiar_control_rpa_afectados(g: Gestion) -> None:
    """Al verificar una gestion carga_inconsistente, la inconsistencia se
    corrigio: los COEs afectados vuelven a reconciliar, asi que su check de
    control RPA pasa de 'inconsistente' a 'ok'. Sin esto el check queda rojo
    para siempre porque el RPA no re-postea el control. No commitea (el caller
    lo hace)."""
    if g.tipo != "carga_inconsistente":
        return
    coes = g.coes_afectados or []
    if not coes:
        return
    (
        LpgDocument.query
        .filter(LpgDocument.coe.in_(coes))
        .filter(LpgDocument.control_rpa_estado == "inconsistente")
        .update({LpgDocument.control_rpa_estado: "ok"}, synchronize_session=False)
    )


# ---------------------------------------------------------------------------
# Marcar realizada (UI personal — SPEC §8.6). pendiente|verificacion_fallida → realizada
# ---------------------------------------------------------------------------


def marcar_realizada(gestion_id: str, usuario: str | None = None) -> dict:
    g = db.session.get(Gestion, gestion_id)
    if g is None:
        raise GestionNoEncontradaError(gestion_id)

    if g.estado not in ("pendiente", "verificacion_fallida"):
        raise TransicionInvalidaError(gestion_id, g.estado, "realizada")

    g.estado = "realizada"
    g.realizada_en = now_cordoba_naive().isoformat()
    g.realizada_por = usuario
    db.session.commit()

    return _serialize(g)
