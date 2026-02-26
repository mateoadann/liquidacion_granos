from datetime import datetime

from ..extensions import db


class AuditEvent(db.Model):
    __tablename__ = "audit_event"

    id = db.Column(db.Integer, primary_key=True)
    taxpayer_id = db.Column(db.Integer, db.ForeignKey("taxpayer.id"), nullable=True)
    operation = db.Column(db.String(80), nullable=True)
    code = db.Column(db.String(30), nullable=True)
    level = db.Column(db.String(20), nullable=False, default="info")
    request_xml = db.Column(db.Text, nullable=True)
    response_xml = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
