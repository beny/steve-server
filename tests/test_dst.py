"""Změna času: hranice dne i trvání aktivit musí přežít přechod CEST/CET.

hamster_day() pracuje s lokálním časem systému, proto testy natvrdo
přepnou TZ na Europe/Prague.
"""

import math
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.activities import day_start_ms, group_activities, hamster_day

CIRC = math.pi * 0.16


@pytest.fixture
def prague_tz():
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Prague"
    time.tzset()
    yield
    if old is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = old
    time.tzset()


def test_autumn_night_is_one_activity_with_real_duration(prague_tz):
    # Noc 24.→25. 10. 2026: ve 3:00 CEST se vrací na 2:00 CET, den má 25 h.
    # Otáčky po hodině od 22:00 CEST do 06:00 CET — na stěně 8 h, reálně 9 h.
    base = datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc)  # 22:00 CEST
    stamps = [
        int((base + timedelta(hours=h)).timestamp() * 1000) for h in range(10)
    ]

    [activity] = group_activities(stamps, CIRC)
    assert activity["day"] == "2026-10-24"
    assert activity["elapsed_s"] == 9 * 3600  # žádná ztracená/přidaná hodina


def test_spring_night_is_one_activity(prague_tz):
    # Noc 28.→29. 3. 2026: ve 2:00 CET skok na 3:00 CEST (23h den).
    base = datetime(2026, 3, 28, 21, 0, tzinfo=timezone.utc)  # 22:00 CET
    stamps = [
        int((base + timedelta(hours=h)).timestamp() * 1000) for h in range(8)
    ]

    [activity] = group_activities(stamps, CIRC)
    assert activity["day"] == "2026-03-28"
    assert activity["elapsed_s"] == 7 * 3600


def test_day_boundary_uses_local_noon_after_switch(prague_tz):
    # 25. 10. odpoledne už platí CET → poledne = 11:00 UTC
    start = day_start_ms("2026-10-25")
    assert datetime.fromtimestamp(start / 1000, timezone.utc).hour == 11
    assert hamster_day(start) == "2026-10-25"
    assert hamster_day(start - 1) == "2026-10-24"

    # den před přechodem je poledne = 10:00 UTC (CEST)
    start = day_start_ms("2026-10-24")
    assert datetime.fromtimestamp(start / 1000, timezone.utc).hour == 10
