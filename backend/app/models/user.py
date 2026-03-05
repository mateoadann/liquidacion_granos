from __future__ import annotations

from ..extensions import db
from ..time_utils import now_cordoba_naive


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="usuario")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=now_cordoba_naive,
        onupdate=now_cordoba_naive,
    )
    last_login_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "nombre": self.nombre,
            "rol": self.rol,
            "activo": self.activo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }
