import math
from datetime import datetime

from app.uploader import build_description, day_is_closed, night_streak

CIRC = math.pi * 0.16


def ms(*args) -> int:
    return int(datetime(*args).timestamp() * 1000)


DAY = "2026-08-16"  # křeččí den: 16. 8. 12:00 – 17. 8. 11:59


def test_closed_after_noon_boundary():
    # po poledni 17. 8. už den nemůže dostat otáčky → uzavřený vždy
    last = ms(2026, 8, 17, 5, 30)
    assert day_is_closed(DAY, last, ms(2026, 8, 17, 12, 1))


def test_closed_morning_after_quiet():
    # skončil v 5:30, v 8:31 je ráno a 3 h ticho → uzavřený
    last = ms(2026, 8, 17, 5, 30)
    assert day_is_closed(DAY, last, ms(2026, 8, 17, 8, 31))


def test_open_morning_quiet_too_short():
    last = ms(2026, 8, 17, 5, 30)
    assert not day_is_closed(DAY, last, ms(2026, 8, 17, 7, 30))


def test_open_night_even_after_long_quiet():
    # 3 h ticho ve 2:30 v noci → ještě může běžet druhou směnu
    last = ms(2026, 8, 16, 23, 30)
    assert not day_is_closed(DAY, last, ms(2026, 8, 17, 2, 45))


def test_open_evening_quiet_is_not_morning():
    # večerní rozcvička 18:00, ticho do 21:10 → noc teprve přijde
    last = ms(2026, 8, 16, 18, 0)
    assert not day_is_closed(DAY, last, ms(2026, 8, 16, 21, 10))


def night(day_of_aug: int, revs: int, gap_s: float = 1.0) -> list[int]:
    base = ms(2026, 8, day_of_aug, 22, 0)
    return [base + int(i * gap_s * 1000) for i in range(revs)]


def test_description_bouts_and_streak():
    base = ms(2026, 8, 16, 22, 0)
    # dva bloky: 10 otáček po 1 s, pak 10 min pauza a 5 otáček
    stamps = [base + i * 1000 for i in range(10)]
    stamps += [base + 700_000 + i * 1000 for i in range(5)]
    days = {"2026-08-15": night(15, 10), "2026-08-16": stamps}

    text = build_description("2026-08-16", days, CIRC)
    longest = f"{10 * CIRC:.0f} m"
    assert text == (
        f"2 runs through the night, longest {longest}.\n"
        "🔥 2 nights in a row."
    )


def test_description_first_night_is_minimal():
    days = {"2026-08-16": night(16, 3)}
    text = build_description("2026-08-16", days, CIRC)
    assert text.startswith("1 run through the night")
    assert "in a row" not in text  # streak 1 se neukazuje


def test_description_fastest_run_picks_quickest_bout():
    base = ms(2026, 8, 16, 22, 0)
    # pomalý blok: 60 otáček po 1 s; po 10 min rychlý: 80 otáček po 0,5 s
    stamps = [base + i * 1000 for i in range(60)]
    fast_base = base + 700_000
    stamps += [fast_base + i * 500 for i in range(80)]
    days = {"2026-08-16": stamps}

    text = build_description("2026-08-16", days, CIRC)
    kmh = CIRC / 0.5 * 3.6
    assert f"Fastest run: {kmh:.1f} km/h avg over {80 * CIRC:.0f} m." in text


def test_description_fastest_run_skips_short_bouts():
    # žádný blok nemá 30 s pohybu → řádek se neukazuje
    days = {"2026-08-16": night(16, 10)}
    text = build_description("2026-08-16", days, CIRC)
    assert "Fastest run" not in text


def test_description_busiest_hour():
    # 22:50–23:10 → víc otáček padne do hodiny 23
    base = ms(2026, 8, 16, 22, 50)
    stamps = [base + i * 60_000 for i in range(21)]
    days = {"2026-08-16": stamps}
    text = build_description("2026-08-16", days, CIRC)
    assert "Busiest hour: 23:00-0:00" in text


def test_description_distance_record_needs_history():
    days = {f"2026-08-{d}": night(d, 5) for d in (12, 13, 14)}
    days["2026-08-15"] = night(15, 8)
    text = build_description("2026-08-15", days, CIRC)
    assert "🏆 New distance record!" in text

    # stejný výkon jako dřív rekord není
    days["2026-08-16"] = night(16, 8)
    text = build_description("2026-08-16", days, CIRC)
    assert "🏆" not in text


def test_description_longest_run_record():
    # stejná vzdálenost, ale poprvé v jednom kuse → rekord bloku, ne distance
    days = {
        f"2026-08-{d}": night(d, 2)
        + [ms(2026, 8, d, 23, 0) + i * 1000 for i in range(2)]
        for d in (12, 13, 14)
    }
    days["2026-08-15"] = night(15, 4)
    text = build_description("2026-08-15", days, CIRC)
    assert "🏆 Longest run ever" in text
    assert "New distance record" not in text


def test_description_lifetime_milestone():
    big_circ = 100.0  # ať netřeba 20k otáček
    days = {"2026-08-15": night(15, 99), "2026-08-16": night(16, 2)}
    text = build_description("2026-08-16", days, big_circ)
    assert "🎉 Lifetime odometer just passed 10 km." in text

    # bez překročení hranice se milník neukazuje
    days["2026-08-17"] = night(17, 2)
    text = build_description("2026-08-17", days, big_circ)
    assert "🎉" not in text


def test_night_streak_counts_consecutive_days():
    days = {"2026-08-12", "2026-08-14", "2026-08-15", "2026-08-16"}
    assert night_streak("2026-08-16", days) == 3  # 13. 8. chybí → streak končí
    assert night_streak("2026-08-12", days) == 1


def test_night_streak_across_month_boundary():
    days = {"2026-07-31", "2026-08-01"}
    assert night_streak("2026-08-01", days) == 2
