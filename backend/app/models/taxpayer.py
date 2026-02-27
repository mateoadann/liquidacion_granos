from datetime import datetime

from ..extensions import db


class Taxpayer(db.Model):
    __tablename__ = "taxpayer"

    id = db.Column(db.Integer, primary_key=True)
    cuit = db.Column(db.String(11), unique=True, nullable=False)
    empresa = db.Column(db.String(255), nullable=False, default="Sin empresa")
    cuit_representado = db.Column(db.String(11), nullable=False, default="")
    clave_fiscal_encrypted = db.Column(db.Text, nullable=False, default="")
    cert_crt_path = db.Column(db.Text, nullable=True)
    cert_key_path = db.Column(db.Text, nullable=True)
    cert_crt_filename = db.Column(db.String(255), nullable=True)
    cert_key_filename = db.Column(db.String(255), nullable=True)
    cert_uploaded_at = db.Column(db.DateTime, nullable=True)
    playwright_enabled = db.Column(db.Boolean, nullable=False, default=True)
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
