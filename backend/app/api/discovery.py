from __future__ import annotations

from flask import Blueprint, jsonify

from ..integrations.arca import ArcaIntegrationError, ArcaWslpgClient

discovery_bp = Blueprint("discovery", __name__)


@discovery_bp.get("/discovery/wslpg/methods")
def discovery_methods():
    try:
        client = ArcaWslpgClient()
        data = client.discovery_summary()
        return jsonify(data)
    except ArcaIntegrationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # fallback inesperado
        return jsonify({"error": f"Error inesperado en discovery: {exc}"}), 500


@discovery_bp.get("/discovery/wslpg/methods/<string:method_name>")
def discovery_method_help(method_name: str):
    try:
        client = ArcaWslpgClient()
        data = client.method_help(method_name)
        return jsonify({"method": method_name, "help": str(data)})
    except ArcaIntegrationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error inesperado consultando method_help: {exc}"}), 500

