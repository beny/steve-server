"""Generování FIT souboru z timestampů otáček jednoho křeččího dne."""

from datetime import datetime, timezone

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import (
    Event,
    EventType,
    FileType,
    Manufacturer,
    Sport,
    SubSport,
)

from .activities import DEBOUNCE_MS, MOVING_GAP_MS


def build_fit(timestamps_ms: list[int], circumference_m: float) -> bytes:
    """Sestaví aktivitu jako indoor ride: record každou sekundu
    s kumulativní vzdáleností a okamžitou rychlostí (0 v pauzách)."""
    start = timestamps_ms[0]
    end = timestamps_ms[-1]

    builder = FitFileBuilder(auto_define=True)

    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.serial_number = 1
    file_id.time_created = start
    builder.add(file_id)

    timer_start = EventMessage()
    timer_start.event = Event.TIMER
    timer_start.event_type = EventType.START
    timer_start.timestamp = start
    builder.add(timer_start)

    moving_ms = 0
    max_speed = 0.0  # m/s
    revolutions_done = 0  # index poslední projeté otáčky
    for t in range(start, end + 1000, 1000):
        t = min(t, end)

        while (
            revolutions_done + 1 < len(timestamps_ms)
            and timestamps_ms[revolutions_done + 1] <= t
        ):
            revolutions_done += 1

        # rychlost = obvod / mezera mezi otáčkami obklopujícími čas t
        speed = 0.0
        if revolutions_done + 1 < len(timestamps_ms):
            gap = timestamps_ms[revolutions_done + 1] - timestamps_ms[revolutions_done]
            if DEBOUNCE_MS <= gap <= MOVING_GAP_MS:
                speed = circumference_m / (gap / 1000)

        record = RecordMessage()
        record.timestamp = t
        record.distance = (revolutions_done + 1) * circumference_m
        record.speed = speed
        builder.add(record)

        if t == end:
            break

    for prev, curr in zip(timestamps_ms, timestamps_ms[1:]):
        gap = curr - prev
        if gap < DEBOUNCE_MS:
            continue
        if gap <= MOVING_GAP_MS:
            moving_ms += gap
            max_speed = max(max_speed, circumference_m / (gap / 1000))

    timer_stop = EventMessage()
    timer_stop.event = Event.TIMER
    timer_stop.event_type = EventType.STOP_ALL
    timer_stop.timestamp = end
    builder.add(timer_stop)

    distance = len(timestamps_ms) * circumference_m
    elapsed_s = (end - start) / 1000
    moving_s = moving_ms / 1000
    avg_speed = distance / moving_s if moving_s > 0 else 0.0

    lap = LapMessage()
    lap.timestamp = end
    lap.start_time = start
    lap.total_elapsed_time = elapsed_s
    lap.total_timer_time = moving_s
    lap.total_distance = distance
    builder.add(lap)

    session = SessionMessage()
    session.timestamp = end
    session.start_time = start
    session.total_elapsed_time = elapsed_s
    session.total_timer_time = moving_s
    session.total_distance = distance
    session.avg_speed = avg_speed
    session.max_speed = max_speed
    session.sport = Sport.CYCLING
    session.sub_sport = SubSport.INDOOR_CYCLING
    session.num_laps = 1
    builder.add(session)

    # lokální čas startu, aby Strava neukazovala UTC; na rozdíl od
    # ostatních timestampů fit-tool nekonvertuje z unix ms — pole chce
    # syrové sekundy od FIT epochy (31. 12. 1989 UTC)
    FIT_EPOCH_S = 631_065_600
    utc_offset_s = int(
        datetime.fromtimestamp(end / 1000).astimezone().utcoffset().total_seconds()
    )

    activity = ActivityMessage()
    activity.timestamp = end
    activity.local_timestamp = end // 1000 + utc_offset_s - FIT_EPOCH_S
    activity.total_timer_time = moving_s
    activity.num_sessions = 1
    builder.add(activity)

    return bytes(builder.build().to_bytes())
