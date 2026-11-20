from datetime import datetime, timedelta, timezone

# Mezera mezi otáčkami, po které se křeček považuje za stojícího
# (stejná logika jako nulování rychlosti na OLED prototypu).
MOVING_GAP_MS = 3_000

# Kratší mezera je fyzicky nereálná — artefakt zákmitu Hall senzoru.
DEBOUNCE_MS = 100


def group_activities(
    timestamps_ms: list[int],
    circumference_m: float,
) -> list[dict]:
    """Seskupí impulzy do maximálně jedné aktivity za den.

    Den se láme v poledne lokálního času, takže noční běhání přes
    půlnoc zůstane jednou aktivitou.
    """
    activities = []
    session: list[int] = []
    session_day = None

    for ts in timestamps_ms:
        day = hamster_day(ts)
        if session and day != session_day:
            activities.append(_summarize(session, session_day, circumference_m))
            session = []
        session_day = day
        session.append(ts)

    if session:
        activities.append(_summarize(session, session_day, circumference_m))

    return activities


def hamster_day(ts_ms: int) -> str:
    """Křeččí den: láme se v poledne, takže noc patří dni, kdy začala."""
    local = datetime.fromtimestamp(ts_ms / 1000)
    return (local - timedelta(hours=12)).date().isoformat()


def day_start_ms(day: str) -> int:
    """Začátek křeččího dne = poledne lokálního času daného data."""
    noon = datetime.strptime(day, "%Y-%m-%d") + timedelta(hours=12)
    return int(noon.timestamp() * 1000)


def hourly_revolutions(timestamps_ms: list[int], day: str) -> list[int]:
    """Otáčky po hodinách křeččího dne, v pořadí 12:00 až 11:00."""
    counts = [0] * 24
    for ts in timestamps_ms:
        if hamster_day(ts) == day:
            local_hour = datetime.fromtimestamp(ts / 1000).hour
            counts[(local_hour - 12) % 24] += 1
    return counts


def _summarize(session: list[int], day: str, circumference_m: float) -> dict:
    revolutions = len(session)
    distance_m = revolutions * circumference_m
    elapsed_ms = session[-1] - session[0]

    moving_ms = 0
    max_speed_kmh = 0.0
    for prev, curr in zip(session, session[1:]):
        gap = curr - prev
        if gap < DEBOUNCE_MS:
            continue
        if gap <= MOVING_GAP_MS:
            moving_ms += gap
            max_speed_kmh = max(max_speed_kmh, circumference_m / (gap / 1000) * 3.6)

    avg_speed_kmh = (
        distance_m / (moving_ms / 1000) * 3.6 if moving_ms > 0 else 0.0
    )

    return {
        "day": day,
        "start": _iso(session[0]),
        "end": _iso(session[-1]),
        "revolutions": revolutions,
        "distance_m": round(distance_m, 1),
        "elapsed_s": round(elapsed_ms / 1000),
        "moving_time_s": round(moving_ms / 1000),
        "avg_speed_kmh": round(avg_speed_kmh, 1),
        "max_speed_kmh": round(max_speed_kmh, 1),
    }


def _iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
