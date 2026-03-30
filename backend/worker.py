from __future__ import annotations

import os
import logging

from redis import Redis
from rq import Queue, Worker

from app import create_app
from app.logging_setup import configure_logging


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    logger = logging.getLogger(__name__)
    app = create_app()
    redis_url = app.config["REDIS_URL"]
    queue_names = [name.strip() for name in os.getenv("RQ_QUEUES", "playwright").split(",") if name.strip()]
    connection = Redis.from_url(redis_url)

    with app.app_context():
        queues = [Queue(name, connection=connection) for name in queue_names]
        logger.info("Worker start | queues=%s redis_url=%s", queue_names, redis_url)
        worker = Worker(queues, connection=connection)
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
