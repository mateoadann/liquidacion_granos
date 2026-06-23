from ..extensions import db
from ..time_utils import now_cordoba_naive


class ExtractionJob(db.Model):
    __tablename__ = "extraction_job"

    id = db.Column(db.Integer, primary_key=True)
    taxpayer_id = db.Column(db.Integer, db.ForeignKey("taxpayer.id"), nullable=False)
    operation = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    payload = db.Column(db.JSON, nullable=True)
    result = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    current_phase = db.Column(db.String(80), nullable=True)
    current_message = db.Column(db.Text, nullable=True)
    failure_phase = db.Column(db.String(80), nullable=True)
    failure_message_user = db.Column(db.Text, nullable=True)
    failure_message_technical = db.Column(db.Text, nullable=True)
    failure_error_type = db.Column(db.String(64), nullable=True)
    failure_code = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=now_cordoba_naive,
        onupdate=now_cordoba_naive,
    )
