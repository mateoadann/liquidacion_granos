import base64
from app.extensions import db
from app.models import ExtractionJob, JobScreenshot
from app.workers.playwright_jobs import _persist_job_screenshot


def test_persist_creates_screenshot(app):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        png = b"\x89PNG\r\n\x1a\nFAKE"
        _persist_job_screenshot(job.id, taxpayer_id=1, png_bytes=png, fase="LOGIN_START")
        shot = JobScreenshot.query.filter_by(extraction_job_id=job.id).first()
        assert shot is not None
        assert base64.b64decode(shot.image_base64) == png
        assert shot.fase == "LOGIN_START"


def test_persist_noop_when_none(app):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        _persist_job_screenshot(job.id, taxpayer_id=1, png_bytes=None, fase=None)
        assert JobScreenshot.query.filter_by(extraction_job_id=job.id).first() is None
