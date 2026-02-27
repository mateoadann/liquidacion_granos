from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from app import create_app

try:
    from app.services.lpg_playwright_pipeline import LpgPlaywrightPipelineService
except ModuleNotFoundError as exc:  # pragma: no cover - defensa runtime
    if exc.name == "playwright":
        print(
            "ERROR: Falta instalar Playwright. Ejecutá: "
            "pip install -r requirements.txt && python -m playwright install chromium",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise


def _parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si"}


def _parse_date_arg(label: str, value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{label} es obligatorio (DD/MM/AAAA).")
    try:
        parsed = datetime.strptime(text, "%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(
            f"Fecha inválida en {label}: '{text}'. Formato esperado: DD/MM/AAAA."
        ) from exc
    return parsed.strftime("%d/%m/%Y")


def _parse_taxpayer_ids(raw_values: list[str]) -> list[int]:
    ids: list[int] = []
    for raw in raw_values:
        for piece in raw.split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                ids.append(int(piece))
            except ValueError as exc:
                raise ValueError(f"taxpayer-id inválido: '{piece}'.") from exc
    unique_ids: list[int] = []
    seen: set[int] = set()
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        unique_ids.append(item)
    return unique_ids


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pipeline Playwright LPG: consulta COEs en ARCA UI y procesa "
            "nuevos con liquidacionXCoeConsultar."
        )
    )
    parser.add_argument(
        "--taxpayer-id",
        action="append",
        default=[],
        help=(
            "ID de cliente a procesar. Se puede repetir o pasar CSV "
            "(ej: --taxpayer-id 1 --taxpayer-id 2,3). "
            "Si no se envía, procesa todos los activos con playwright_enabled=true."
        ),
    )
    parser.add_argument("--fecha-desde", required=True, help="Fecha desde (DD/MM/AAAA).")
    parser.add_argument("--fecha-hasta", required=True, help="Fecha hasta (DD/MM/AAAA).")
    parser.add_argument("--headless", action="store_true", help="Forzar ejecución headless.")
    parser.add_argument("--headed", action="store_true", help="Forzar ejecución con navegador visible.")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000")),
        help="Timeout general por paso en milisegundos (default: 30000).",
    )
    parser.add_argument(
        "--type-delay-ms",
        type=int,
        default=int(os.getenv("PLAYWRIGHT_TYPE_DELAY_MS", "80")),
        help="Delay de tipeo para el buscador de servicios ARCA (default: 80).",
    )
    parser.add_argument("--output-json", help="Path para guardar salida JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        fecha_desde = _parse_date_arg("fecha-desde", args.fecha_desde)
        fecha_hasta = _parse_date_arg("fecha-hasta", args.fecha_hasta)
        taxpayer_ids = _parse_taxpayer_ids(args.taxpayer_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.headed and args.headless:
        print("ERROR: No podés usar --headless y --headed juntos.", file=sys.stderr)
        return 2

    if args.headed:
        headless = False
    elif args.headless:
        headless = True
    else:
        headless = _parse_bool_env("PLAYWRIGHT_HEADLESS", True)

    app = create_app()
    with app.app_context():
        result = LpgPlaywrightPipelineService().run(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            taxpayer_ids=taxpayer_ids or None,
            headless=headless,
            timeout_ms=args.timeout_ms,
            type_delay_ms=args.type_delay_ms,
        )

    body = result.to_dict()
    output = json.dumps(body, ensure_ascii=False, indent=2)
    print(output)

    if args.output_json:
        out_path = Path(args.output_json).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Resultado guardado en: {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
