from __future__ import annotations

import logging


def configure_logging(level_name: str | None) -> None:
    level_text = str(level_name or "INFO").upper()
    level = getattr(logging, level_text, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )

    logging.getLogger("rq.worker").setLevel(level)
    logging.getLogger("rq.queue").setLevel(level)
    logging.getLogger("rq.job").setLevel(level)
