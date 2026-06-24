from __future__ import annotations

from datetime import timedelta


def _create_taxpayer(db, Taxpayer):
    tp = Taxpayer(
        cuit="20111111199",
        empresa="Jitter SA",
        cuit_representado="30711165378",
        activo=True,
        scheduler_activo=True,
        scheduler_dias_semana="lun,mar,mie,jue,vie,sab,dom",
        scheduler_hora_local="03:00",
        scheduler_dias_extraccion=90,
        playwright_enabled=True,
        clave_fiscal_encrypted="x",
    )
    db.session.add(tp)
    db.session.commit()
    return tp


def test_disparar_usa_enqueue_in_con_delay_en_ventana(app, mocker):
    with app.app_context():
        from app.extensions import db
        from app.models import Taxpayer
        from app.services import scheduler_service

        app.config["SCHEDULER_JITTER_WINDOW_SECONDS"] = 10800
        tp = _create_taxpayer(db, Taxpayer)

        fake_queue = mocker.MagicMock()
        fake_rq_job = mocker.MagicMock()
        fake_rq_job.id = "rq-123"
        fake_queue.name = "playwright"
        fake_queue.enqueue_in.return_value = fake_rq_job
        mocker.patch.object(scheduler_service, "get_queue", return_value=fake_queue)
        # delay determinístico
        mocker.patch.object(scheduler_service.random, "randint", return_value=4242)

        job = scheduler_service._disparar_extraccion(tp)

        fake_queue.enqueue_in.assert_called_once()
        delta_arg = fake_queue.enqueue_in.call_args.args[0]
        assert delta_arg == timedelta(seconds=4242)
        assert job.payload["jitter_delay_seconds"] == 4242


def test_delay_nunca_excede_la_ventana(app, mocker):
    with app.app_context():
        from app.extensions import db
        from app.models import Taxpayer
        from app.services import scheduler_service

        app.config["SCHEDULER_JITTER_WINDOW_SECONDS"] = 100
        tp = _create_taxpayer(db, Taxpayer)

        fake_queue = mocker.MagicMock()
        fake_queue.name = "playwright"
        fake_queue.enqueue_in.return_value = mocker.MagicMock(id="x")
        mocker.patch.object(scheduler_service, "get_queue", return_value=fake_queue)
        spy = mocker.spy(scheduler_service.random, "randint")

        scheduler_service._disparar_extraccion(tp)

        # randint llamado con (0, 100)
        assert spy.call_args.args == (0, 100)
