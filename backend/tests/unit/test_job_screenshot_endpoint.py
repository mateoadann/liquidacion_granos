import base64
from app.extensions import db
from app.models import ExtractionJob, JobScreenshot


def _mk_job_with_shot(app, with_shot=True):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        if with_shot:
            db.session.add(JobScreenshot(
                extraction_job_id=job.id, taxpayer_id=1,
                image_base64=base64.b64encode(b"\x89PNGFAKE").decode("ascii"),
                fase="LOGIN_START",
            ))
            db.session.commit()
        return job.id


def test_screenshot_requires_auth(app, client):
    jid = _mk_job_with_shot(app)
    res = client.get(f"/api/jobs/{jid}/screenshot")
    assert res.status_code == 401


def test_screenshot_returns_png(app, client, auth_headers):
    jid = _mk_job_with_shot(app)
    res = client.get(f"/api/jobs/{jid}/screenshot", headers=auth_headers)
    assert res.status_code == 200
    assert res.mimetype == "image/png"


def test_screenshot_404_when_absent(app, client, auth_headers):
    jid = _mk_job_with_shot(app, with_shot=False)
    res = client.get(f"/api/jobs/{jid}/screenshot", headers=auth_headers)
    assert res.status_code == 404


def test_job_serializer_has_tiene_screenshot(app, client, auth_headers):
    jid = _mk_job_with_shot(app)
    res = client.get(f"/api/jobs/{jid}", headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["tiene_screenshot"] is True
