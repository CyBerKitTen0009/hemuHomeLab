import copy
import json
import time

import pytest

from backend.hcc.models import DeviceInput


MAC = {"name": "MacBook Air", "host": "macbook-air.local", "kind": "macos", "mode": "agent", "git_paths": ["/Users/test/project"]}
REPORT = {
    "hostname": "macbook-air", "os": "macOS", "kernel": "25.0.0",
    "metrics": {"cpu_percent": 8.0, "cpu_count": 8, "memory_percent": 50, "memory_total": 16000, "memory_used": 8000, "disk_percent": 25, "network_rx": 10, "network_tx": 20, "load": [1, 2, 3], "uptime": 400, "disks": [{"mount": "/", "total": 100000, "used": 25000, "percent": 25}]},
    "git": [{"path": "/Users/test/project", "name": "project", "branch": "main", "commit": "abc123", "message": "update", "dirty": False}],
}


def enroll(auth):
    response = auth.post("/api/devices", json=MAC)
    assert response.status_code == 201
    device = response.json()
    response = auth.post(f"/api/devices/{device['id']}/agent-token")
    assert response.status_code == 200
    return device["id"], response.json()["token"]


def test_agent_credentials_are_bound_to_device_and_not_admin(auth):
    ident, token = enroll(auth)
    other, other_token = enroll(auth)
    headers = {"Authorization": "Bearer " + token}
    base = f"/api/agents/{ident}"
    assert auth.get(base + "/config").status_code == 401  # Admin cookie is insufficient.
    assert auth.get(base + "/config", headers=headers).json()["git_paths"] == MAC["git_paths"]
    assert auth.get(f"/api/agents/{other}/config", headers=headers).status_code == 401
    assert auth.post(base + "/snapshot", json=REPORT, headers={"Authorization": "Bearer " + other_token}).status_code == 401
    with auth.app.state.db.connect() as conn:
        stored = conn.execute("SELECT token_hash FROM agent_tokens WHERE device_id=?", (ident,)).fetchone()[0]
    assert stored != token and len(stored) == 64
    assert token not in json.dumps(auth.get("/api/config/backup").json())
    assert token not in json.dumps(auth.get("/api/audit").json())
    auth.post("/api/logout")
    assert auth.get("/api/devices", headers=headers).status_code == 401
    assert auth.post(f"/api/devices/{ident}/agent-token", headers=headers).status_code == 401
    assert auth.get(base + "/config", headers=headers).status_code == 200


def test_agent_history_freshness_rate_limit_and_no_remote_actions(auth, monkeypatch):
    ident, token = enroll(auth)
    base = f"/api/agents/{ident}"
    headers = {"Authorization": "Bearer " + token}
    response = auth.post(base + "/snapshot", json=REPORT, headers=headers)
    assert response.status_code == 200
    history = auth.get(f"/api/devices/{ident}/history").json()
    assert len(history) == 1
    assert auth.post(base + "/snapshot", json=REPORT, headers=headers).status_code == 429
    assert auth.post(f"/api/devices/{ident}/refresh").json()["status"] == "online"
    assert len(auth.get(f"/api/devices/{ident}/history").json()) == 1
    assert auth.get(f"/api/devices/{ident}/logs").status_code == 422
    auth.app.state.settings.poll_seconds = 30
    now = time.time()
    monkeypatch.setattr("backend.hcc.agents.time.time", lambda: now + 121)
    device = next(item for item in auth.get("/api/devices").json() if item["id"] == ident)
    assert device["snapshot"]["status"] == "offline"
    assert device["snapshot"]["error"]["code"] == "agent_offline"
    assert device["snapshot"]["timestamp"] == history[0]["timestamp"]
    assert device["snapshot"]["metrics"]["cpu_percent"] == 8
    assert auth.get(f"/api/devices/{ident}/history").json() == history


def test_agent_token_rotation_deletion_and_restore_revoke_access(auth):
    ident, old = enroll(auth)
    endpoint = f"/api/agents/{ident}/config"
    token = auth.post(f"/api/devices/{ident}/agent-token").json()["token"]
    assert auth.get(endpoint, headers={"Authorization": "Bearer " + old}).status_code == 401
    assert auth.get(endpoint, headers={"Authorization": "Bearer " + token}).status_code == 200
    backup = auth.get("/api/config/backup").json()
    assert auth.post("/api/config/restore", json=backup).status_code == 200
    assert auth.get(endpoint, headers={"Authorization": "Bearer " + token}).status_code == 401
    token = auth.post(f"/api/devices/{ident}/agent-token").json()["token"]
    assert auth.delete(f"/api/devices/{ident}").status_code == 200
    assert auth.get(endpoint, headers={"Authorization": "Bearer " + token}).status_code == 401


def test_agent_label_changes_preserve_identity_credentials_and_history(auth):
    ident, token = enroll(auth)
    headers = {"Authorization": "Bearer " + token}
    assert auth.post(f"/api/agents/{ident}/snapshot", json=REPORT, headers=headers).status_code == 200
    before = auth.get(f"/api/devices/{ident}/history").json()
    assert auth.put(f"/api/devices/{ident}", json={**MAC, "name": "Travelling Mac", "host": "new-label.local"}).status_code == 200
    assert auth.get(f"/api/agents/{ident}/config", headers=headers).status_code == 200
    assert auth.get(f"/api/devices/{ident}/history").json() == before


@pytest.mark.parametrize("change", ["unknown_repo", "duplicate_repo", "command", "invalid_metric"])
def test_agent_rejects_unconfigured_payload_and_invalid_metrics(auth, change):
    ident, token = enroll(auth)
    report = copy.deepcopy(REPORT)
    if change == "unknown_repo":
        report["git"][0]["path"] = "/Users/test/private"
    elif change == "duplicate_repo":
        report["git"].append(report["git"][0])
    elif change == "command":
        report["command"] = "arbitrary"
    else:
        report["metrics"]["cpu_percent"] = "NaN"
    assert auth.post(f"/api/agents/{ident}/snapshot", json=report, headers={"Authorization": "Bearer " + token}).status_code == 422
    assert auth.get(f"/api/devices/{ident}/history").json() == []


def test_agent_connection_mode_change_revokes_token(auth):
    ident, token = enroll(auth)
    assert auth.put(f"/api/devices/{ident}", json={**MAC, "mode": "demo", "kind": "linux"}).status_code == 200
    assert auth.get(f"/api/agents/{ident}/config", headers={"Authorization": "Bearer " + token}).status_code == 401
    with auth.app.state.db.connect() as conn:
        assert conn.execute("SELECT 1 FROM agent_tokens WHERE device_id=?", (ident,)).fetchone() is None


def test_agent_configuration_restrictions_and_token_csrf(auth):
    ident, _ = enroll(auth)
    for change in [{"kind": "linux"}, {"health_targets": [{"name": "API", "url": "http://localhost/"}]}, {"jump_device_id": "demo-thinkbook"}]:
        assert auth.post("/api/devices", json={**MAC, **change}).status_code == 422
    auth.headers.pop("X-CSRF-Token")
    assert auth.post(f"/api/devices/{ident}/agent-token").status_code == 403
