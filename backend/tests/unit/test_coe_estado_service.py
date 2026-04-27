from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.extensions import db
from app.models.coe_estado import CoeEstado
from app.models.lpg_document import LpgDocument
from app.models.taxpayer import Taxpayer
from app.services.coe_estado_service import (
    HashMismatchError,
    TransicionInvalidaError,
    calcular_hash,
    consultar_estado,
    crear_pendiente,
    listar_estados,
    marcar_descargado,
    reportar_cargado,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _create_taxpayer(cuit="20111111112", cuit_representado="30711165378", **kwargs):
    defaults = {
        "cuit": cuit,
        "empresa": "Test SA",
        "cuit_representado": cuit_representado,
    }
    defaults.update(kwargs)
    tp = Taxpayer(**defaults)
    db.session.add(tp)
    db.session.commit()
    return tp


def _create_lpg_document(taxpayer, coe="33020030787127", **kwargs):
    defaults = {
        "taxpayer_id": taxpayer.id,
        "coe": coe,
        "estado": "AC",
        "datos_limpios": {"cuit_comprador": "30502874353"},
    }
    defaults.update(kwargs)
    doc = LpgDocument(**defaults)
    db.session.add(doc)
    db.session.commit()
    return doc


def _create_test_coe_estado(
    coe="33020030787127", estado="pendiente", cuit_empresa="30711165378", **kwargs
):
    entry = CoeEstado(coe=coe, cuit_empresa=cuit_empresa, estado=estado, **kwargs)
    db.session.add(entry)
    db.session.commit()
    return entry


# ---------------------------------------------------------------------------
# Hash tests
# ---------------------------------------------------------------------------


class TestCalcularHash:
    def test_stable(self):
        data = {"campo_a": 1, "campo_b": "valor"}
        assert calcular_hash(data) == calcular_hash(data)

    def test_excludes_metadata(self):
        base = {"campo_a": 1, "campo_b": "valor"}
        with_meta = {**base, "estado_origen": "pendiente", "id_liquidacion": "abc-123"}
        assert calcular_hash(base) == calcular_hash(with_meta)

    def test_detects_changes(self):
        data_a = {"campo_a": 1, "campo_b": "valor"}
        data_b = {"campo_a": 2, "campo_b": "valor"}
        assert calcular_hash(data_a) != calcular_hash(data_b)

    def test_hash_contract_fixture(self):
        """Verifica el hash contra el fixture compartido con rpa-holistor."""
        fixture_path = FIXTURES_DIR / "hash_contract.json"
        contract = json.loads(fixture_path.read_text())

        for case in contract["test_cases"]:
            result = calcular_hash(case["input"])
            assert result.startswith("sha256:")

            if case["expected_hash"] is not None:
                assert result == case["expected_hash"]
            else:
                # Primer run: escribe el hash para compartir
                case["expected_hash"] = result
                fixture_path.write_text(
                    json.dumps(contract, indent=2, ensure_ascii=False) + "\n"
                )


# ---------------------------------------------------------------------------
# crear_pendiente
# ---------------------------------------------------------------------------


class TestCrearPendiente:
    def test_creates_entry(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            doc = _create_lpg_document(tp)
            entry = crear_pendiente(doc)

            assert entry is not None
            assert entry.coe == "33020030787127"
            assert entry.estado == "pendiente"
            assert entry.cuit_empresa == "30711165378"
            assert entry.cuit_comprador == "30502874353"
            assert entry.lpg_document_id == doc.id

    def test_skip_existing(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            doc = _create_lpg_document(tp)
            crear_pendiente(doc)
            result = crear_pendiente(doc)
            assert result is None
            assert CoeEstado.query.count() == 1


# ---------------------------------------------------------------------------
# marcar_descargado
# ---------------------------------------------------------------------------


class TestMarcarDescargado:
    def test_pendiente_to_descargado(self, app):
        with app.app_context():
            _create_test_coe_estado(coe="111", estado="pendiente")
            entry = marcar_descargado("111", "sha256:abc", "liq-001")

            assert entry.estado == "descargado"
            assert entry.hash_payload_emitido == "sha256:abc"
            assert entry.id_liquidacion == "liq-001"
            assert entry.descargado_en is not None


# ---------------------------------------------------------------------------
# reportar_cargado
# ---------------------------------------------------------------------------


class TestReportarCargado:
    def test_ok(self, app):
        with app.app_context():
            _create_test_coe_estado(
                coe="222",
                estado="descargado",
                hash_payload_emitido="sha256:match",
            )
            result = reportar_cargado({
                "coe": "222",
                "ejecucion_id": "run-1",
                "usuario": "bot@test",
                "cargado_en": "2026-04-22T10:00:00",
                "estado": "ok",
                "hash_payload": "sha256:match",
                "comprobante": {
                    "codigo": "F2",
                    "tipo_pto_vta": 3302,
                    "nro": 30384112,
                    "fecha_emision": "2026-02-26",
                },
            })
            assert result["duplicado"] is False
            assert result["estado"] == "cargado"

            entry = CoeEstado.query.filter_by(coe="222").first()
            assert entry.codigo_comprobante == "F2"
            assert entry.tipo_pto_vta == 3302
            assert entry.nro_comprobante == 30384112

    def test_error(self, app):
        with app.app_context():
            _create_test_coe_estado(coe="333", estado="descargado")
            result = reportar_cargado({
                "coe": "333",
                "ejecucion_id": "run-2",
                "usuario": "bot@test",
                "estado": "error",
                "hash_payload": "sha256:xyz",
                "error_fase": "login",
                "error_mensaje": "Credenciales inválidas",
            })
            assert result["duplicado"] is False
            assert result["estado"] == "error"

            entry = CoeEstado.query.filter_by(coe="333").first()
            assert entry.error_fase == "login"
            assert entry.error_mensaje == "Credenciales inválidas"

    def test_idempotent(self, app):
        with app.app_context():
            _create_test_coe_estado(
                coe="444",
                estado="cargado",
                ultima_ejecucion_id="run-1",
                hash_payload_cargado="sha256:same",
            )
            result = reportar_cargado({
                "coe": "444",
                "ejecucion_id": "run-1",
                "estado": "ok",
                "hash_payload": "sha256:same",
            })
            assert result["duplicado"] is True

    def test_hash_mismatch(self, app):
        with app.app_context():
            _create_test_coe_estado(
                coe="555",
                estado="descargado",
                hash_payload_emitido="sha256:original",
            )
            with pytest.raises(HashMismatchError):
                reportar_cargado({
                    "coe": "555",
                    "ejecucion_id": "run-3",
                    "estado": "ok",
                    "hash_payload": "sha256:tampered",
                })


# ---------------------------------------------------------------------------
# Transición inválida
# ---------------------------------------------------------------------------


class TestTransicionInvalida:
    def test_pendiente_to_cargado(self, app):
        with app.app_context():
            _create_test_coe_estado(
                coe="666",
                estado="pendiente",
                hash_payload_emitido="sha256:x",
            )
            with pytest.raises(TransicionInvalidaError):
                reportar_cargado({
                    "coe": "666",
                    "ejecucion_id": "run-4",
                    "estado": "ok",
                    "hash_payload": "sha256:x",
                })


# ---------------------------------------------------------------------------
# consultar_estado
# ---------------------------------------------------------------------------


class TestConsultarEstado:
    def test_found(self, app):
        with app.app_context():
            _create_test_coe_estado(coe="777", estado="pendiente")
            result = consultar_estado("777")
            assert result is not None
            assert result["coe"] == "777"
            assert result["estado"] == "pendiente"

    def test_not_found(self, app):
        with app.app_context():
            result = consultar_estado("999999")
            assert result is None


# ---------------------------------------------------------------------------
# listar_estados
# ---------------------------------------------------------------------------


class TestListarEstados:
    def test_with_filters(self, app):
        with app.app_context():
            _create_test_coe_estado(coe="A01", cuit_empresa="30711165378", estado="pendiente")
            _create_test_coe_estado(coe="A02", cuit_empresa="30711165378", estado="cargado")
            _create_test_coe_estado(coe="A03", cuit_empresa="20999999999", estado="pendiente")

            result = listar_estados(cuit_empresa="30711165378", estado="pendiente")
            assert result["total"] == 1
            assert result["items"][0]["coe"] == "A01"

    def test_no_filters(self, app):
        with app.app_context():
            _create_test_coe_estado(coe="B01")
            _create_test_coe_estado(coe="B02")

            result = listar_estados()
            assert result["total"] == 2
            assert len(result["items"]) == 2
