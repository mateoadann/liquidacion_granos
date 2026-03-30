from __future__ import annotations

from ..extensions import db
from ..time_utils import now_cordoba_naive


class WslpgParameter(db.Model):
    """Tabla parametrica sincronizada desde WSLPG (granos, puertos, etc)."""

    __tablename__ = "wslpg_parameter"
    __table_args__ = (
        db.UniqueConstraint("tabla", "codigo", name="uq_wslpg_param_tabla_codigo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tabla = db.Column(db.String(60), nullable=False, index=True)
    codigo = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.String(255), nullable=False, default="")
    datos_extra = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive, onupdate=now_cordoba_naive)

    @classmethod
    def lookup(cls, tabla: str, codigo: str | int) -> str | None:
        row = cls.query.filter_by(tabla=tabla, codigo=str(codigo)).first()
        return row.descripcion if row else None

    @classmethod
    def lookup_map(cls, tabla: str) -> dict[str, str]:
        rows = cls.query.filter_by(tabla=tabla).all()
        return {row.codigo: row.descripcion for row in rows}
