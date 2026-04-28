from ..extensions import db
from ..time_utils import now_cordoba_naive


class CoeEstado(db.Model):
    __tablename__ = "coe_estado"

    id = db.Column(db.Integer, primary_key=True)
    coe = db.Column(db.String(20), unique=True, nullable=False, index=True)
    lpg_document_id = db.Column(
        db.Integer,
        db.ForeignKey("lpg_document.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    cuit_empresa = db.Column(db.String(11), nullable=False)
    cuit_comprador = db.Column(db.String(11), nullable=True)
    codigo_comprobante = db.Column(db.String(10), nullable=True)
    tipo_pto_vta = db.Column(db.Integer, nullable=True)
    nro_comprobante = db.Column(db.Integer, nullable=True)
    fecha_emision = db.Column(db.String(20), nullable=True)
    id_liquidacion = db.Column(db.String(50), unique=True, nullable=True)

    estado = db.Column(db.String(20), nullable=False, default="pendiente")
    descargado_en = db.Column(db.DateTime, nullable=True)
    cargado_en = db.Column(db.DateTime, nullable=True)
    error_mensaje = db.Column(db.Text, nullable=True)
    error_fase = db.Column(db.String(20), nullable=True)

    ultima_ejecucion_id = db.Column(db.String(50), nullable=True)
    ultimo_usuario = db.Column(db.String(100), nullable=True)
    hash_payload_emitido = db.Column(db.String(100), nullable=True)
    hash_payload_cargado = db.Column(db.String(100), nullable=True)

    actualizado_en = db.Column(
        db.DateTime,
        nullable=False,
        default=now_cordoba_naive,
        onupdate=now_cordoba_naive,
    )

    document = db.relationship(
        "LpgDocument",
        backref=db.backref("coe_estado", uselist=False),
    )

    __table_args__ = (
        db.Index("idx_coe_estado_empresa_estado", "cuit_empresa", "estado"),
    )
