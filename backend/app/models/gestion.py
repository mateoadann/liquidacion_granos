from ..extensions import db
from ..time_utils import now_cordoba_naive


class Gestion(db.Model):
    """Gestión de dato maestro faltante (SPEC §8.1).

    El ``gestion_id`` es la PK y lo calcula/manda rpa-holistor de forma
    determinística (SPEC §3). granos solo lo recibe, nunca lo genera.
    """

    __tablename__ = "gestiones"

    gestion_id = db.Column(db.Text, primary_key=True)  # 'g_' + 16 hex (§3)
    tipo = db.Column(db.Text, nullable=False)  # alta_cliente | alta_proveedor | mapeo_grano | alta_cuenta
    cuit_empresa = db.Column(db.Text, nullable=False)  # solo dígitos
    razon_social = db.Column(db.Text, nullable=True)
    identificador = db.Column(db.Text, nullable=False)  # CUIT | cod_grano | alias
    descripcion = db.Column(db.Text, nullable=False)
    # ponytail: JSON nativo en vez de TEXT+json.loads manual (Postgres lo soporta,
    # el contrato HTTP no cambia). En SQLite de tests db.JSON degrada a TEXT y SQLAlchemy
    # serializa/deserializa igual.
    datos_contexto = db.Column(db.JSON, nullable=True)
    coes_afectados = db.Column(db.JSON, nullable=True)  # array de COEs (14 díg.)

    estado = db.Column(db.Text, nullable=False, default="pendiente")
    detectado_en = db.Column(db.Text, nullable=False)  # ISO 8601 con TZ, lo manda RPA
    realizada_en = db.Column(db.Text, nullable=True)
    realizada_por = db.Column(db.Text, nullable=True)
    verificada_en = db.Column(db.Text, nullable=True)
    verificacion_detalle = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)
    actualizado_en = db.Column(
        db.DateTime,
        nullable=False,
        default=now_cordoba_naive,
        onupdate=now_cordoba_naive,
    )

    __table_args__ = (
        db.Index("idx_gestiones_empresa_estado", "cuit_empresa", "estado"),
        db.Index("idx_gestiones_estado", "estado"),
    )
