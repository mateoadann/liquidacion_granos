from ..extensions import db
from ..time_utils import now_cordoba_naive


class JobScreenshot(db.Model):
    __tablename__ = "job_screenshot"

    id = db.Column(db.Integer, primary_key=True)
    extraction_job_id = db.Column(
        db.Integer,
        db.ForeignKey("extraction_job.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    taxpayer_id = db.Column(db.Integer, db.ForeignKey("taxpayer.id"), nullable=True)
    image_base64 = db.Column(db.Text, nullable=False)
    fase = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)
