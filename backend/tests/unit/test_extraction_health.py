from app.services.extraction_health import classify, ACTIONABLE_CODES, RED_THRESHOLD_DAYS


def test_classify_completed_recent_is_green():
    estado, accionable = classify(
        last_status="completed", failure_code=None, dias_sin_exito=0
    )
    assert estado == "verde"
    assert accionable is False


def test_classify_auth_failed_is_red_day_one():
    estado, accionable = classify(
        last_status="failed", failure_code="AUTH_FAILED", dias_sin_exito=1
    )
    assert estado == "rojo"
    assert accionable is True


def test_classify_transient_one_day_is_yellow():
    estado, accionable = classify(
        last_status="failed", failure_code="NETWORK_ERROR", dias_sin_exito=1
    )
    assert estado == "amarillo"
    assert accionable is False


def test_classify_transient_three_days_escalates_to_red():
    estado, accionable = classify(
        last_status="failed", failure_code="NETWORK_ERROR", dias_sin_exito=3
    )
    assert estado == "rojo"
    assert accionable is False  # rojo por antigüedad, no por causa accionable


def test_classify_failed_without_code_is_grey():
    estado, accionable = classify(
        last_status="failed", failure_code=None, dias_sin_exito=5
    )
    assert estado == "gris"
    assert accionable is False


def test_classify_no_jobs_is_grey():
    estado, accionable = classify(
        last_status=None, failure_code=None, dias_sin_exito=None
    )
    assert estado == "gris"
    assert accionable is False


def test_actionable_codes_are_the_red_ones():
    assert ACTIONABLE_CODES == {"AUTH_FAILED", "SERVICE_NOT_ADHERED", "EMPRESA_NOT_FOUND"}


def test_red_threshold_is_three():
    assert RED_THRESHOLD_DAYS == 3


from datetime import timedelta
from app.services.extraction_health import compute_health
from app.extensions import db
from app.models import Taxpayer, ExtractionJob
from app.time_utils import now_cordoba_naive


def _mk_taxpayer(app, empresa, activo=True):
    with app.app_context():
        t = Taxpayer(empresa=empresa, cuit="20111111110", activo=activo)
        db.session.add(t)
        db.session.commit()
        return t.id


def _mk_job(app, taxpayer_id, status, days_ago, failure_code=None, user_msg=None):
    with app.app_context():
        ts = now_cordoba_naive() - timedelta(days=days_ago)
        j = ExtractionJob(
            taxpayer_id=taxpayer_id,
            operation="scheduler_lpg_extract",
            status=status,
            created_at=ts,
            finished_at=ts,
            failure_code=failure_code,
            failure_message_user=user_msg,
        )
        db.session.add(j)
        db.session.commit()


def test_compute_health_green_for_recent_success(app):
    tid = _mk_taxpayer(app, "Cliente Verde")
    _mk_job(app, tid, "completed", days_ago=0)
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["estado"] == "verde"
    assert row["dias_sin_exito"] == 0
    assert row["empresa"] == "Cliente Verde"
    assert "cuit" not in row


def test_compute_health_red_for_auth_failed(app):
    tid = _mk_taxpayer(app, "Cliente Auth")
    _mk_job(app, tid, "completed", days_ago=8)
    _mk_job(app, tid, "failed", days_ago=1, failure_code="AUTH_FAILED",
            user_msg="La clave fiscal de la empresa parece ser incorrecta.")
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["estado"] == "rojo"
    assert row["es_accionable"] is True
    assert row["causa_codigo"] == "AUTH_FAILED"
    assert row["dias_sin_exito"] == 8


def test_compute_health_never_extracted_is_grey(app):
    tid = _mk_taxpayer(app, "Cliente Nuevo")
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["estado"] == "gris"
    assert row["dias_sin_exito"] is None
    assert row["ultima_ok"] is None


def test_compute_health_excludes_inactive(app):
    tid = _mk_taxpayer(app, "Cliente Inactivo", activo=False)
    _mk_job(app, tid, "failed", days_ago=1, failure_code="AUTH_FAILED")
    with app.app_context():
        out = compute_health()
    assert all(c["taxpayer_id"] != tid for c in out["clientes"])


def test_compute_health_resumen_counts(app):
    out_tid = _mk_taxpayer(app, "Cliente Resumen")
    _mk_job(app, out_tid, "completed", days_ago=0)
    with app.app_context():
        out = compute_health()
    assert out["resumen"]["verde"] >= 1
    assert set(out["resumen"].keys()) == {"verde", "amarillo", "rojo", "gris"}
