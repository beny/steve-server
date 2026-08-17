from fastapi.testclient import TestClient

from app import db
from app.main import app


def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    return TestClient(app)


def test_heartbeat_on_empty_db_has_no_latest(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        resp = c.post(
            "/pulses",
            json={"boot_id": "b1", "sent_at_ticks": 1000, "pulses_ticks": []},
        ).json()
        assert resp["stored"] == 0
        assert resp["latest"] is None
        assert resp["day"]


def test_latest_reflects_stored_pulses(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        resp = c.post(
            "/pulses",
            json={
                "boot_id": "b1",
                "sent_at_ticks": 10_000,
                "pulses_ticks": [8_000, 8_500, 9_000],
            },
        ).json()
        assert resp["stored"] == 3
        assert resp["latest"]["revolutions"] == 3

        # heartbeat vrací tytéž součty — displej z nich žije i v klidu
        resp = c.post(
            "/pulses",
            json={"boot_id": "b1", "sent_at_ticks": 40_000, "pulses_ticks": []},
        ).json()
        assert resp["latest"]["revolutions"] == 3
