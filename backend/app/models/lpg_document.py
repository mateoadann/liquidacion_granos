from ..extensions import db
from ..time_utils import now_cordoba_naive


class LpgDocument(db.Model):
    __tablename__ = "lpg_document"

    id = db.Column(db.Integer, primary_key=True)
    taxpayer_id = db.Column(db.Integer, db.ForeignKey("taxpayer.id"), nullable=False)
    coe = db.Column(db.String(20), nullable=True, index=True)
    pto_emision = db.Column(db.Integer, nullable=True)
    nro_orden = db.Column(db.BigInteger, nullable=True)
    estado = db.Column(db.String(10), nullable=True)
    tipo_documento = db.Column(db.String(30), nullable=False, default="LPG")
    raw_data = db.Column(db.JSON, nullable=True)
    datos_limpios = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)

    # Controlada — locally audited in Holistor flag
    controlada = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.text("false"),
    )
    controlada_por = db.Column(db.String(80), nullable=True)
    controlada_por_nombre = db.Column(db.String(255), nullable=True)
    controlada_en = db.Column(db.DateTime, nullable=True)

    # Control RPA — reconciliation verdict reported by rpa-holistor.
    # null = no RPA check; "ok" = reconciled; "inconsistente" = mismatch
    # (detail lives in the carga_inconsistente gestion); "no_encontrado" = COE
    # not found in Holistor. Independent from the manual `controlada` flag.
    control_rpa_estado = db.Column(db.String(20), nullable=True)
    control_rpa_en = db.Column(db.DateTime, nullable=True)
