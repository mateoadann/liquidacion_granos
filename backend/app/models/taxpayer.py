from datetime import datetime

from ..extensions import db


class Taxpayer(db.Model):
    __tablename__ = "taxpayer"

    id = db.Column(db.Integer, primary_key=True)
    cuit = db.Column(db.String(11), unique=True, nullable=False)
    razon_social = db.Column(db.String(255), nullable=True)
    ambiente = db.Column(db.String(20), nullable=False, default="homologacion")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    extraction_jobs = db.relationship(
        "ExtractionJob", backref="taxpayer", lazy=True, cascade="all,delete-orphan"
    )
    documents = db.relationship(
        "LpgDocument", backref="taxpayer", lazy=True, cascade="all,delete-orphan"
    )
    audit_events = db.relationship(
        "AuditEvent", backref="taxpayer", lazy=True, cascade="all,delete-orphan"
    )
