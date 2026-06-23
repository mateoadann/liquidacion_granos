from datetime import timedelta

from app.extensions import db
from app.models import Taxpayer, ExtractionJob
from app.services.scheduler_service import reactivar_pausados_por_auth
from app.time_utils import now_cordoba_naive
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


def test_reactivates_when_clave_updated_after_error(app):
    ahora = now_cordoba_naive()
    tid = _mk_taxpayer(
        app,
        scheduler_activo=False,
        scheduler_pausado_por_auth=True,
        scheduler_ultimo_error_en=ahora - timedelta(days=2),
        clave_fiscal_actualizada_en=ahora,  # clave actualizada DESPUÉS del error
    )
    with app.app_context():
        n = reactivar_pausados_por_auth()
        t = Taxpayer.query.get(tid)
        assert n == 1
        assert t.scheduler_activo is True
        assert t.scheduler_pausado_por_auth is False


def test_no_reactivate_when_clave_not_updated(app):
    ahora = now_cordoba_naive()
    tid = _mk_taxpayer(
        app,
        scheduler_activo=False,
        scheduler_pausado_por_auth=True,
        scheduler_ultimo_error_en=ahora,
        clave_fiscal_actualizada_en=ahora - timedelta(days=2),  # clave vieja
    )
    with app.app_context():
        reactivar_pausados_por_auth()
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is False
        assert t.scheduler_pausado_por_auth is True


def test_no_reactivate_manual_pause(app):
    ahora = now_cordoba_naive()
    tid = _mk_taxpayer(
        app,
        scheduler_activo=False,
        scheduler_pausado_por_auth=False,  # pausa MANUAL
        scheduler_ultimo_error_en=ahora - timedelta(days=2),
        clave_fiscal_actualizada_en=ahora,
    )
    with app.app_context():
        reactivar_pausados_por_auth()
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is False  # no se toca
