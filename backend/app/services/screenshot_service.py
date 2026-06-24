from __future__ import annotations

import logging
from datetime import timedelta

from ..extensions import db
from ..models import JobScreenshot
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)


def purge_old_screenshots(max_age_days: int) -> int:
    """Borra los JobScreenshot con created_at más viejo que max_age_days.
    Devuelve la cantidad borrada.
    """
    cutoff = now_cordoba_naive() - timedelta(days=max_age_days)
    deleted = (
        JobScreenshot.query.filter(JobScreenshot.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    if deleted:
        db.session.commit()
        logger.info("SCREENSHOT_PURGE | borrados=%s cutoff=%s", deleted, cutoff)
    return deleted
