import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db
from .activities import day_start_ms, group_activities, hamster_day
from .config import TICKS_PERIOD, WHEEL_CIRCUMFERENCE_M
from .uploader import upload_loop


class PulseBatch(BaseModel):
    boot_id: str
    sent_at_ticks: int = Field(ge=0, lt=TICKS_PERIOD)
    pulses_ticks: list[int] = Field(max_length=10_000)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    task = asyncio.create_task(upload_loop())
    yield
    task.cancel()


app = FastAPI(title="Steve Server", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def dashboard_page():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return FileResponse(Path(__file__).parent / "static" / "apple-touch-icon.png")


@app.get("/icon.svg", include_in_schema=False)
def browser_icon():
    return FileResponse(Path(__file__).parent / "static" / "icon.svg", media_type="image/svg+xml")


@app.get("/api/dashboard")
def dashboard_data():
    """Součty a posledních 14 křeččích dnů pro webový přehled."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    current_day = hamster_day(now_ms)
    total_revolutions, last_ms = db.pulse_overview()

    latest = None
    if last_ms is not None:
        latest_stamps = db.pulse_timestamps_since(
            day_start_ms(hamster_day(last_ms))
        )
        latest = group_activities(latest_stamps, WHEEL_CIRCUMFERENCE_M)[-1]

    first_day = (date.fromisoformat(current_day) - timedelta(days=13)).isoformat()
    recent_stamps = db.pulse_timestamps_since(day_start_ms(first_day))
    history = group_activities(recent_stamps, WHEEL_CIRCUMFERENCE_M)

    return {
        "day": current_day,
        "latest": latest,
        "total_revolutions": total_revolutions,
        "total_distance_m": round(total_revolutions * WHEEL_CIRCUMFERENCE_M, 1),
        "history": history,
    }


@app.post("/pulses")
def receive_pulses(batch: PulseBatch):
    """Přijme dávku otáček s relativními ticks_ms z ESP.

    Absolutní čas se odvodí od času přijetí: stáří impulzu je rozdíl
    sent_at_ticks - ticks v aritmetice MicroPythonu (wrap na 2^30).
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rows = []
    for ticks in batch.pulses_ticks:
        age_ms = (batch.sent_at_ticks - ticks) % TICKS_PERIOD
        rows.append((batch.boot_id, ticks, now_ms - age_ms))

    stored = db.insert_pulses(rows)
    # ESP nemá hodiny ani vlastní čítače — DIST/TIME na displeji jsou
    # "latest": součty posledního dne s otáčkami. Dokud Steve v novém
    # dni neběžel, ukazuje se tak celá minulá noc; první večerní otáčkou
    # se displej přirozeně přepne (resetne) na nový den.
    return {
        "received": len(rows),
        "stored": stored,
        "day": hamster_day(now_ms),
        "latest": _latest_day_stats(),
    }


def _latest_day_stats() -> dict | None:
    last = db.last_pulse_ts()
    if last is None:
        return None
    stamps = db.pulse_timestamps_since(day_start_ms(hamster_day(last)))
    [activity] = group_activities(stamps, WHEEL_CIRCUMFERENCE_M)
    return activity


@app.get("/activities")
def activities():
    """Impulzy seskupené do aktivit — max jedna za den (poledne–poledne)."""
    timestamps = db.pulse_timestamps()
    return group_activities(timestamps, WHEEL_CIRCUMFERENCE_M)
