"""Detekce uzavřených křeččích dnů a jejich odeslání na Stravu."""

import asyncio
import logging
from datetime import date, datetime, timedelta

from . import db, fit, strava
from .activities import MOVING_GAP_MS, hamster_day
from .config import MORNING_HOUR, QUIET_HOURS, UPLOAD_CHECK_S, WHEEL_CIRCUMFERENCE_M

log = logging.getLogger("steve.uploader")

QUIET_MS = QUIET_HOURS * 3600 * 1000

# Pauza delší než 5 minut odděluje běžecké bloky (pro popis aktivity).
BOUT_GAP_MS = 5 * 60 * 1000


def day_is_closed(day: str, last_pulse_ms: int, now_ms: int) -> bool:
    """Den je uzavřený, když už běží pozdější křeččí den (po poledni
    do něj nemůže nic přibýt), nebo když je ráno a Steve dostatečně
    dlouho neběhá — noční zvíře už za světla nezačne."""
    if hamster_day(now_ms) != day:
        return True

    now_local = datetime.fromtimestamp(now_ms / 1000)
    is_morning = MORNING_HOUR <= now_local.hour < 12
    return is_morning and now_ms - last_pulse_ms >= QUIET_MS


def _format_m(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.0f} m"


def night_streak(day: str, days_with_data: set[str]) -> int:
    """Kolik nocí v řadě (včetně této) Steve běhal."""
    count = 1
    d = date.fromisoformat(day)
    while (d - timedelta(days=count)).isoformat() in days_with_data:
        count += 1
    return count


def _bouts(stamps: list[int]) -> list[list[int]]:
    """Timestampy rozdělené do běžeckých bloků."""
    bouts: list[list[int]] = []
    for i, ts in enumerate(stamps):
        if i == 0 or ts - stamps[i - 1] > BOUT_GAP_MS:
            bouts.append([])
        bouts[-1].append(ts)
    return bouts


def _bout_sizes(stamps: list[int]) -> list[int]:
    return [len(b) for b in _bouts(stamps)]


def _fastest_run(stamps: list[int], circumference_m: float) -> tuple[float, float] | None:
    """(km/h, metry) nejrychlejšího bloku s aspoň 30 s pohybu."""
    best = None
    for bout in _bouts(stamps):
        moving_ms = 0
        moving_revs = 0  # otáčky ujeté během započteného pohybu (mezery)
        for prev, curr in zip(bout, bout[1:]):
            gap = curr - prev
            if gap <= MOVING_GAP_MS:
                moving_ms += gap
                moving_revs += 1
        if moving_ms < 30_000:
            continue
        kmh = moving_revs * circumference_m / (moving_ms / 1000) * 3.6
        if best is None or kmh > best[0]:
            best = (kmh, len(bout) * circumference_m)
    return best


def build_description(
    day: str,
    days: dict[str, list[int]],
    circumference_m: float,
) -> str:
    """Popis aktivity ze syrových otáček a historie: bloky, nejrušnější
    hodina, srovnání s předchozí nocí, streak, rekordy a milníky."""
    stamps = days[day]
    bouts = _bout_sizes(stamps)
    longest_m = max(bouts) * circumference_m
    runs = f"{len(bouts)} run{'s' if len(bouts) != 1 else ''}"
    lines = [f"{runs} through the night, longest {_format_m(longest_m)}."]

    # nejrušnější hodina — mění se noc od noci
    by_hour: dict[int, int] = {}
    for ts in stamps:
        hour = datetime.fromtimestamp(ts / 1000).hour
        by_hour[hour] = by_hour.get(hour, 0) + 1
    if len(by_hour) > 1:
        top_hour, revs = max(by_hour.items(), key=lambda kv: kv[1])
        lines.append(
            f"Busiest hour: {top_hour}:00-{(top_hour + 1) % 24}:00"
            f" ({_format_m(revs * circumference_m)})."
        )

    fastest = _fastest_run(stamps, circumference_m)
    if fastest:
        kmh, distance_m = fastest
        lines.append(
            f"Fastest run: {kmh:.1f} km/h avg over {_format_m(distance_m)}."
        )

    earlier = sorted(d for d in days if d < day)

    streak = night_streak(day, set(days))
    if streak >= 2:
        lines.append(f"🔥 {streak} nights in a row.")

    # rekordy až po pár nocích, jinak je rekord každá druhá
    if len(earlier) >= 3:
        if len(stamps) > max(len(days[d]) for d in earlier):
            lines.append("🏆 New distance record!")
        best_bout = max(max(_bout_sizes(days[d])) for d in earlier)
        if max(bouts) > best_bout:
            lines.append(
                f"🏆 Longest run ever: {_format_m(longest_m)}!"
            )

    # milník celkového nájezdu po 10 km
    before_m = sum(len(days[d]) for d in earlier) * circumference_m
    after_m = before_m + len(stamps) * circumference_m
    if int(before_m // 10_000) < int(after_m // 10_000):
        km = int(after_m // 10_000) * 10
        lines.append(f"🎉 Lifetime odometer just passed {km} km.")

    return "\n".join(lines)


def run_once(now_ms: int) -> list[str]:
    """Nahraje všechny uzavřené neodeslané dny. Vrací, které odešly."""
    days: dict[str, list[int]] = {}
    for ts in db.pulse_timestamps():
        days.setdefault(hamster_day(ts), []).append(ts)

    uploaded = db.uploaded_days()
    sent = []
    for day in sorted(days):
        stamps = days[day]
        if day in uploaded or not day_is_closed(day, stamps[-1], now_ms):
            continue

        name = "Night Shift"
        description = build_description(day, days, WHEEL_CIRCUMFERENCE_M)
        fit_data = fit.build_fit(stamps, WHEEL_CIRCUMFERENCE_M)
        upload_id = strava.upload_activity(
            fit_data, name, description, external_id=f"steve-{day}"
        )
        db.mark_uploaded(day, upload_id, now_ms)
        sent.append(day)
        log.info("den %s odeslán na Stravu (upload %s)", day, upload_id)

    return sent


async def upload_loop() -> None:
    while True:
        if strava.configured():
            now_ms = int(datetime.now().timestamp() * 1000)
            try:
                await asyncio.to_thread(run_once, now_ms)
            except Exception:
                log.exception("upload na Stravu selhal, zkusím to znovu")
        await asyncio.sleep(UPLOAD_CHECK_S)
