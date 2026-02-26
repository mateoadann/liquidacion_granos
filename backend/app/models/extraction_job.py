from datetime import datetime

from ..extensions import db


class ExtractionJob(db.Model):
    __tablename__ = "extraction_job"

    id = db.Column(db.Integer, primary_key=True)
    taxpayer_id = db.Column(db.Integer, db.ForeignKey("taxpayer.id"), nullable=False)
    operation = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    payload = db.Column(db.JSON, nullable=True)
    result = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
