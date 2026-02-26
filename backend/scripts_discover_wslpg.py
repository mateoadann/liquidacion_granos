"""
Discovery real de métodos WSLPG usando arca_arg.

Uso:
  python scripts_discover_wslpg.py

Variables recomendadas:
  ARCA_CUIT_REPRESENTADA=...
  ARCA_ENVIRONMENT=homologacion|produccion
  ARCA_CERT_PATH=/ruta/cert.crt
  ARCA_KEY_PATH=/ruta/private.key
  ARCA_KEY_PASSPHRASE=...
  ARCA_TA_PATH=/ruta/cache_ta
"""

from __future__ import annotations

import json
import os
import traceback


def main() -> None:
    try:
        from app.integrations.arca import ArcaIntegrationError, ArcaWslpgClient
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"No se pudo importar integración ARCA: {exc}",
                    "tip": "Ejecutá el script dentro del entorno backend con dependencias instaladas.",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    try:
        client = ArcaWslpgClient()
        config_preview = {
            "environment": client.config.environment,
            "service_name": client.config.service_name,
            "wsdl_url": client.config.wsdl_url,
            "cuit_representada": client.config.cuit_representada,
            "cert_path": client.config.cert_path,
            "key_path": client.config.key_path,
            "ta_path": client.config.ta_path,
        }
        summary = client.discovery_summary()
        methods = summary["methods"]

        payload = {
            "ok": True,
            "config": config_preview,
            "summary": summary,
            "sample_method_help": {},
        }

        for method_name in methods[:5]:
            try:
                payload["sample_method_help"][method_name] = str(
                    client.method_help(method_name)
                )
            except Exception as exc:
                payload["sample_method_help"][method_name] = f"error: {exc}"

        print(json.dumps(payload, indent=2, ensure_ascii=False))
    except ArcaIntegrationError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "config": {
                        "ARCA_ENVIRONMENT": os.getenv("ARCA_ENVIRONMENT"),
                        "ARCA_SERVICE_NAME": os.getenv("ARCA_SERVICE_NAME"),
                        "ARCA_WSDL_URL": os.getenv("ARCA_WSDL_URL"),
                        "ARCA_CUIT_REPRESENTADA": os.getenv("ARCA_CUIT_REPRESENTADA"),
                        "ARCA_CERT_PATH": os.getenv("ARCA_CERT_PATH"),
                        "ARCA_KEY_PATH": os.getenv("ARCA_KEY_PATH"),
                        "ARCA_TA_PATH": os.getenv("ARCA_TA_PATH"),
                    },
                    "error": str(exc),
                    "tip": "Revisá variables ARCA_* y que arca_arg esté instalado.",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
