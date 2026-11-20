from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import db
from app.activities import hamster_day
from app.main import app


def test_dashboard_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Steve" in page.text
        assert "<title>Steve</title>" in page.text
        assert 'rel="apple-touch-icon"' in page.text
        assert "/api/dashboard" in page.text

        icon = client.get("/apple-touch-icon.png")
        assert icon.status_code == 200
        assert icon.headers["content-type"] == "image/png"
        assert icon.content.startswith(b"\x89PNG\r\n\x1a\n")

        result = client.get("/api/dashboard")
        assert result.status_code == 200
        assert result.json()["total_revolutions"] == 0
        assert result.json()["latest"] is None
        assert result.json()["history"] == []
        assert result.json()["hourly_revolutions"] == [0] * 24


def test_dashboard_shows_saved_pulse(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as client:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        db.insert_pulses([("test-boot", 123, now_ms - 1000)])

        result = client.get("/api/dashboard").json()
        assert result["total_revolutions"] == 1
        assert result["total_distance_m"] > 0
        assert result["latest"]["day"] == hamster_day(now_ms - 1000)
        assert result["latest"]["revolutions"] == 1
        assert result["history"][-1] == result["latest"]
        if result["latest"]["day"] == result["day"]:
            hour = datetime.fromtimestamp((now_ms - 1000) / 1000).hour
            assert result["hourly_revolutions"][(hour - 12) % 24] == 1
