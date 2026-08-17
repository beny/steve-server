import math

from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage

from app.fit import build_fit

CIRC = math.pi * 0.16
START = 1_786_898_519_000


def test_fit_roundtrip():
    # 5 otáček po 0,5 s, pak 5 s pauza a poslední otáčka
    stamps = [START + int(i * 500) for i in range(5)] + [START + 7_000]
    data = build_fit(stamps, CIRC)

    fit_file = FitFile.from_bytes(data)
    records = [
        r.message for r in fit_file.records if isinstance(r.message, RecordMessage)
    ]
    [session] = [
        r.message for r in fit_file.records if isinstance(r.message, SessionMessage)
    ]

    # record každou sekundu od první do poslední otáčky
    assert len(records) == 8
    assert records[0].timestamp == START
    assert records[-1].timestamp == START + 7_000

    # kumulativní vzdálenost končí na počtu otáček × obvod
    assert abs(records[-1].distance - 6 * CIRC) < 0.01

    # uprostřed pauzy je rychlost nula, při běhu ~1 m/s
    assert records[0].speed > 0.9
    assert records[4].speed == 0

    assert abs(session.total_distance - 6 * CIRC) < 0.01
    assert abs(session.total_timer_time - 2.0) < 0.01  # moving jen sprint
    assert abs(session.total_elapsed_time - 7.0) < 0.01
