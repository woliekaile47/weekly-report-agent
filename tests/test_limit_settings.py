"""The settings API updates the employee file without changing other rules."""

from pathlib import Path

from fastapi.testclient import TestClient

from report_agent import api, config


def test_editable_limits_preserve_other_rules_and_reject_stale_edits(tmp_path, monkeypatch):
    for relative in ("config/employee.yaml", "config/columns.yaml", "skills/weekly-report/SKILL.md"):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((config.ROOT / relative).read_bytes())
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    client = TestClient(api.app)
    before = client.get("/api/config").json()
    path = Path(tmp_path / "config/employee.yaml")
    original = path.read_text(encoding="utf-8")
    values = {
        "version": before["version"],
        "model_calls": 12,
        "model_timeout_seconds": 120,
        "active_seconds": 900,
    }
    response = client.put("/api/limits", json=values)
    assert response.status_code == 200
    assert response.json()["limits"] == before["employee"]["limits"] | {
        "model_calls": 12,
        "model_timeout_seconds": 120,
        "active_seconds": 900,
    }
    saved = client.get("/api/config").json()
    assert saved["employee"]["limits"]["model_calls"] == 12
    assert saved["employee"]["limit_reasons"] == before["employee"]["limit_reasons"]
    assert saved["employee"]["quality"] == before["employee"]["quality"]
    assert "model_calls: 8" in original and "model_calls: 12" in path.read_text(encoding="utf-8")

    stale = client.put("/api/limits", json=values)
    assert stale.status_code == 409
    invalid = client.put("/api/limits", json={**values, "version": saved["version"], "model_calls": 0})
    assert invalid.status_code == 422
    assert client.get("/api/config").json()["version"] == saved["version"]
