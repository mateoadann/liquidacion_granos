from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import Taxpayer

API_KEY = "test-integration-key"
URL = "/api/v2/empresas"


@pytest.fixture()
def api_headers():
    return {"X-API-Key": API_KEY}


def _create_taxpayer(
    *,
    cuit: str = "20304050607",
    cuit_representado: str = "30711165378",
    activo: bool = True,
    scheduler_activo: bool = True,
    scheduler_dias_semana: str = "lun,mar,mie,jue,vie",
    scheduler_hora_local: str = "06:00",
    scheduler_ultimo_ok: datetime | None = None,
    scheduler_ultimo_error: str | None = None,
    empresa: str = "Acopio SA",
) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit_representado
    item.clave_fiscal_encrypted = "test"
    item.activo = activo
    item.scheduler_activo = scheduler_activo
    item.scheduler_dias_semana = scheduler_dias_semana
    item.scheduler_hora_local = scheduler_hora_local
    item.scheduler_ultimo_ok = scheduler_ultimo_ok
    item.scheduler_ultimo_error = scheduler_ultimo_error
    db.session.add(item)
    db.session.commit()
    return item


# -----------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------


def test_get_sin_api_key_devuelve_401(client):
    resp = client.get(URL)
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "api_key_invalida"


# -----------------------------------------------------------------------
# Lista solo taxpayers activos
# -----------------------------------------------------------------------


def test_get_lista_solo_taxpayers_activos(client, app, api_headers):
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111", cuit_representado="30111111111", empresa="Alpha SA"
        )
        _create_taxpayer(
            cuit="20222222222", cuit_representado="30222222222", empresa="Beta SA"
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    cuits = {e["cuit_empresa"] for e in data["empresas"]}
    assert cuits == {"30111111111", "30222222222"}


def test_get_excluye_taxpayers_con_activo_false(client, app, api_headers):
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111",
            cuit_representado="30111111111",
            empresa="Alpha SA",
            activo=True,
        )
        _create_taxpayer(
            cuit="20222222222",
            cuit_representado="30222222222",
            empresa="Beta SA",
            activo=False,
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    cuits = {e["cuit_empresa"] for e in data["empresas"]}
    assert cuits == {"30111111111"}


# -----------------------------------------------------------------------
# Diferencia clave con /v2/liquidaciones: incluye scheduler_activo=False
# -----------------------------------------------------------------------


def test_get_incluye_taxpayers_con_scheduler_activo_false(client, app, api_headers):
    """A diferencia de /v2/liquidaciones, /v2/empresas SÍ incluye scheduler off."""
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111",
            cuit_representado="30111111111",
            empresa="Alpha SA",
            scheduler_activo=True,
        )
        _create_taxpayer(
            cuit="20222222222",
            cuit_representado="30222222222",
            empresa="Beta SA",
            scheduler_activo=False,
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    by_cuit = {e["cuit_empresa"]: e for e in data["empresas"]}
    assert by_cuit["30111111111"]["scheduler"]["activo"] is True
    assert by_cuit["30222222222"]["scheduler"]["activo"] is False


# -----------------------------------------------------------------------
# Scheduler config completa
# -----------------------------------------------------------------------


def test_get_incluye_scheduler_config_completa(client, app, api_headers):
    ultimo_ok = datetime(2026, 5, 13, 6, 12, 33)
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111",
            cuit_representado="30111111111",
            empresa="Alpha SA",
            scheduler_activo=True,
            scheduler_dias_semana="lun,mie,vie",
            scheduler_hora_local="07:30",
            scheduler_ultimo_ok=ultimo_ok,
            scheduler_ultimo_error="timeout en pagina ARCA",
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    empresa = data["empresas"][0]
    assert empresa["cuit_empresa"] == "30111111111"
    assert empresa["razon_social"] == "Alpha SA"
    sched = empresa["scheduler"]
    assert sched["activo"] is True
    assert sched["dias_semana"] == ["lun", "mie", "vie"]
    assert sched["hora_local"] == "07:30"
    assert sched["ultimo_scrape_ok"] == ultimo_ok.isoformat()
    assert sched["ultimo_scrape_error"] == "timeout en pagina ARCA"


def test_get_dias_semana_se_devuelve_como_lista(client, app, api_headers):
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111",
            cuit_representado="30111111111",
            empresa="Alpha SA",
            scheduler_dias_semana="lun,mar,mie,jue,vie",
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    dias = data["empresas"][0]["scheduler"]["dias_semana"]
    assert isinstance(dias, list)
    assert dias == ["lun", "mar", "mie", "jue", "vie"]


# -----------------------------------------------------------------------
# Ultimo scrape global
# -----------------------------------------------------------------------


def test_get_ultimo_scrape_global_es_max_de_taxpayers(client, app, api_headers):
    older = datetime(2026, 5, 10, 6, 0, 0)
    newer = datetime(2026, 5, 14, 6, 0, 0)
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111",
            cuit_representado="30111111111",
            empresa="Alpha SA",
            scheduler_ultimo_ok=older,
        )
        _create_taxpayer(
            cuit="20222222222",
            cuit_representado="30222222222",
            empresa="Beta SA",
            scheduler_ultimo_ok=newer,
        )
        _create_taxpayer(
            cuit="20333333333",
            cuit_representado="30333333333",
            empresa="Gamma SA",
            scheduler_ultimo_ok=None,
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ultimo_scrape_global"] == newer.isoformat()


def test_get_ultimo_scrape_global_es_null_si_ningun_taxpayer_corrio(
    client, app, api_headers
):
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111",
            cuit_representado="30111111111",
            empresa="Alpha SA",
            scheduler_ultimo_ok=None,
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ultimo_scrape_global"] is None


# -----------------------------------------------------------------------
# Orden alfabético
# -----------------------------------------------------------------------


def test_get_ordena_por_empresa_alfabetico(client, app, api_headers):
    with app.app_context():
        _create_taxpayer(
            cuit="20333333333", cuit_representado="30333333333", empresa="Zeta SA"
        )
        _create_taxpayer(
            cuit="20111111111", cuit_representado="30111111111", empresa="Alpha SA"
        )
        _create_taxpayer(
            cuit="20222222222", cuit_representado="30222222222", empresa="Mu SA"
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    nombres = [e["razon_social"] for e in data["empresas"]]
    assert nombres == ["Alpha SA", "Mu SA", "Zeta SA"]


# -----------------------------------------------------------------------
# Defensive: cuit_representado vacío
# -----------------------------------------------------------------------


def test_get_excluye_taxpayers_con_cuit_vacio(client, app, api_headers):
    with app.app_context():
        _create_taxpayer(
            cuit="20111111111",
            cuit_representado="30111111111",
            empresa="Alpha SA",
        )
        _create_taxpayer(
            cuit="20222222222",
            cuit_representado="",
            empresa="Beta SA",
        )

    resp = client.get(URL, headers=api_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert data["empresas"][0]["cuit_empresa"] == "30111111111"
