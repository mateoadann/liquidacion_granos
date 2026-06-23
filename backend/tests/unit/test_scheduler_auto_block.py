from app.extensions import db
from app.models import Taxpayer, ExtractionJob
from app.workers.playwright_jobs import _actualizar_scheduler_status


def _mk_taxpayer(app, **kwargs):
    with app.app_context():
        defaults = dict(empresa="Test SA", cuit="20111111110",
                        cuit_representado="30111111110", scheduler_activo=True)
        defaults.update(kwargs)
        t = Taxpayer(**defaults)
        db.session.add(t)
        db.session.commit()
        return t.id


def _mk_job(app, taxpayer_id, operation, failure_code):
    with app.app_context():
        j = ExtractionJob(taxpayer_id=taxpayer_id, operation=operation,
                          status="failed", failure_code=failure_code)
        db.session.add(j)
        db.session.commit()
        return ExtractionJob.query.get(j.id)


def test_auth_failed_blocks_scheduler(app):
    tid = _mk_taxpayer(app)
    with app.app_context():
        job = _mk_job(app, tid, "scheduler_lpg_extract", "AUTH_FAILED")
        _actualizar_scheduler_status(job, final_status="failed", error_text="clave mal")
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is False
        assert t.scheduler_pausado_por_auth is True


def test_timeout_does_not_block(app):
    tid = _mk_taxpayer(app)
    with app.app_context():
        job = _mk_job(app, tid, "scheduler_lpg_extract", "TRANSIENT_LOGIN")
        _actualizar_scheduler_status(job, final_status="failed", error_text="timeout")
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is True
        assert t.scheduler_pausado_por_auth is False


def test_none_failure_code_does_not_block(app):
    tid = _mk_taxpayer(app)
    with app.app_context():
        job = _mk_job(app, tid, "scheduler_lpg_extract", None)
        _actualizar_scheduler_status(job, final_status="failed", error_text="desconocido")
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is True
        assert t.scheduler_pausado_por_auth is False


def test_manual_auth_failed_does_not_block(app):
    tid = _mk_taxpayer(app)
    with app.app_context():
        job = _mk_job(app, tid, "playwright_lpg_run", "AUTH_FAILED")
        _actualizar_scheduler_status(job, final_status="failed", error_text="clave mal")
        t = Taxpayer.query.get(tid)
        # operation no-scheduler: el hook retorna temprano, no toca el scheduler
        assert t.scheduler_activo is True
        assert t.scheduler_pausado_por_auth is False
