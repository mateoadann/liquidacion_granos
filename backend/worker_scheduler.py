"""Worker dedicado que corre `tick_scheduler()` periódicamente.

Loop infinito que evalúa cada minuto qué empresas matchean dia/hora actual
y encola un ExtractionJob por cada una.

Despliegue: container dedicado en docker-compose. Reiniciable.

Parte de PR6 del plan v2 (spec_v2_implementacion_liquidador_granos.md §5).
"""
from __future__ import annotations

import logging
import os
import time

from app import create_app
from app.services.scheduler_service import reconcile_stale_jobs, tick_scheduler
from app.services.screenshot_service import purge_old_screenshots

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("scheduler_worker")

INTERVAL_SECONDS = int(os.environ.get("SCHEDULER_TICK_INTERVAL_SECONDS", "60"))


def main() -> None:
    app = create_app()
    with app.app_context():
        logger.info("scheduler_worker arrancado, tick cada %ds", INTERVAL_SECONDS)
        while True:
            try:
                resumen = tick_scheduler()
                if resumen["disparados"]:
                    logger.info("tick: %s", resumen)
                else:
                    logger.debug("tick vacío (evaluados=%d)", resumen["evaluados"])
            except Exception:
                logger.exception("scheduler tick falló")
            try:
                reconcile_stale_jobs()
            except Exception:
                logger.exception("reconcile_stale_jobs falló")
            try:
                from flask import current_app
                # ponytail: corre cada tick; el DELETE por fecha es barato (índice en created_at) e idempotente
                purge_old_screenshots(current_app.config["SCREENSHOT_RETENTION_DAYS"])
            except Exception:
                logger.exception("purge_old_screenshots falló")
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
