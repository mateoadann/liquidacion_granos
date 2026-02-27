from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

CORDOBA_TZ = ZoneInfo("America/Argentina/Cordoba")


def now_cordoba_aware() -> datetime:
    return datetime.now(CORDOBA_TZ)


def now_cordoba_naive() -> datetime:
    return now_cordoba_aware().replace(tzinfo=None)
