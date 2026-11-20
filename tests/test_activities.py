import math
from datetime import datetime, timedelta

from app.activities import day_start_ms, group_activities, hamster_day, hourly_revolutions

CIRC = math.pi * 0.16

# Základ v lokálním čase, večer — bezpečně uvnitř jednoho křeččího dne
BASE = datetime(2026, 8, 16, 22, 0, 0)


def ts(seconds: float) -> int:
    return int((BASE + timedelta(seconds=seconds)).timestamp() * 1000)


def test_empty_input():
    assert group_activities([], CIRC) == []


def test_single_session_stats():
    # 5 otáček po 0,5 s → 4 mezery à 500 ms, rychlost ~3,6 km/h
    stamps = [ts(i * 0.5) for i in range(5)]
    [activity] = group_activities(stamps, CIRC)

    assert activity["day"] == "2026-08-16"
    assert activity["revolutions"] == 5
    assert activity["distance_m"] == round(5 * CIRC, 1)
    assert activity["elapsed_s"] == 2
    assert activity["moving_time_s"] == 2
    assert activity["avg_speed_kmh"] == round(5 * CIRC / 2 * 3.6, 1)
    assert activity["max_speed_kmh"] == round(CIRC / 0.5 * 3.6, 1)


def test_night_over_midnight_is_one_activity():
    # 23:59 a 00:01 → pořád jeden křeččí den (láme se v poledne)
    stamps = [ts(0), ts(2 * 3600), ts(4 * 3600)]  # 22:00, 00:00, 02:00
    [activity] = group_activities(stamps, CIRC)
    assert activity["day"] == "2026-08-16"
    assert activity["revolutions"] == 3


def test_splits_at_noon_boundary():
    # 22:00 dnes vs. 22:00 zítra → dvě aktivity
    stamps = [ts(0), ts(1), ts(24 * 3600), ts(24 * 3600 + 1)]
    first, second = group_activities(stamps, CIRC)
    assert first["day"] == "2026-08-16"
    assert second["day"] == "2026-08-17"
    assert first["revolutions"] == 2
    assert second["revolutions"] == 2


def test_pause_not_counted_as_moving():
    # 4 s pauza: aktivita drží pohromadě, ale moving time ji nepočítá
    stamps = [ts(0), ts(1), ts(5), ts(6)]
    [activity] = group_activities(stamps, CIRC)
    assert activity["elapsed_s"] == 6
    assert activity["moving_time_s"] == 2


def test_day_start_is_noon_boundary():
    start = day_start_ms("2026-08-16")
    assert hamster_day(start) == "2026-08-16"
    assert hamster_day(start - 1) == "2026-08-15"


def test_debounce_glitch_ignored_in_speed():
    # 50 ms mezera je zákmit — nesmí vystřelit max_speed
    stamps = [ts(0), ts(0.05), ts(0.55)]
    [activity] = group_activities(stamps, CIRC)
    assert activity["max_speed_kmh"] == round(CIRC / 0.5 * 3.6, 1)


def test_hourly_revolutions_run_from_noon_to_noon():
    stamps = [ts(0), ts(3600), ts(2 * 3600), ts(13 * 3600), ts(14 * 3600)]
    counts = hourly_revolutions(stamps, "2026-08-16")

    assert len(counts) == 24
    assert counts[10] == 1  # 22:00
    assert counts[11] == 1  # 23:00
    assert counts[12] == 1  # 00:00
    assert counts[23] == 1  # 11:00 další den
    assert sum(counts) == 4  # 12:00 už patří následujícímu dni
