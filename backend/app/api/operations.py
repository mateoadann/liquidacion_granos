from flask import Blueprint, jsonify

operations_bp = Blueprint("operations", __name__)


@operations_bp.get("/operations")
def list_operations_stub():
    # Base inicial; el discovery real se expone en /api/discovery/wslpg/methods
    core_operations = [
        "liquidacionXCoeConsultar",
        "liquidacionXNroOrdenConsultar",
        "liquidacionUltimoNroOrdenConsultar",
        "liquidacionAutorizar",
        "liquidacionAjustarUnificado",
        "lpgAnularContraDocumento",
        "lpgAutorizarAnticipo",
        "lpgCancelarAnticipo",
    ]
    return jsonify(
        {
            "message": "Matriz base de operaciones WSLPG (MVP).",
            "core_operations": core_operations,
            "discovery_endpoint": "/api/discovery/wslpg/methods",
            "source": "/docs/base_funcional_tecnica_wslpg.md",
        }
    )
