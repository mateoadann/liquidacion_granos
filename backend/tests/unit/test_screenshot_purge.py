import base64
from datetime import timedelta
from app.extensions import db
from app.models import ExtractionJob, JobScreenshot
from app.time_utils import now_cordoba_naive
from app.services.screenshot_service import purge_old_screenshots


def _mk_shot(app, days_ago):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        shot = JobScreenshot(
            extraction_job_id=job.id, taxpayer_id=1,
            image_base64=base64.b64encode(b"X").decode("ascii"),
            created_at=now_cordoba_naive() - timedelta(days=days_ago),
        )
        db.session.add(shot)
        db.session.commit()
        return shot.id


def test_purge_deletes_old_keeps_recent(app):
    old_id = _mk_shot(app, days_ago=5)
    recent_id = _mk_shot(app, days_ago=1)
    with app.app_context():
        n = purge_old_screenshots(max_age_days=3)
        assert n == 1
        assert JobScreenshot.query.get(old_id) is None
        assert JobScreenshot.query.get(recent_id) is not None
