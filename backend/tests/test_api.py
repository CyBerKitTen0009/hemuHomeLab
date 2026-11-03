import json
import time

import pytest

from backend.hcc.models import DeviceInput
from backend.hcc.security import redact

DEVICE = {"name": "New ThinkBook", "host": "hemu-server.top", "port": 2222, "username": "testuser", "mode": "ssh", "credential_ref": "thinkbook"}


def test_authentication_cookie_csrf_and_expiry(client, auth):
    assert "HttpOnly" in auth.post("/api/login", json={"username":"admin", "password":"test-only-long-password-12345"}).headers["set-cookie"]
    assert "SameSite=strict" in auth.post("/api/login", json={"username":"admin", "password":"test-only-long-password-12345"}).headers["set-cookie"]
    auth.headers.pop("X-CSRF-Token")
    assert auth.post("/api/devices", json=DEVICE).status_code == 403
    with auth.app.state.db.connect() as conn:
        conn.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
    assert auth.get("/api/devices").status_code == 401


def test_public_endpoints_expose_no_private_data(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    for endpoint in ["/api/devices", "/api/audit", "/api/config/backup", "/api/session", "/api/devices/demo-thinkbook/logs"]:
        assert client.get(endpoint).status_code == 401
    assert client.post("/api/execute", json={"command": "whoami"}).status_code == 404


def test_cross_site_and_host_protection(auth):
    assert auth.post("/api/devices", json=DEVICE, headers={"Origin": "https://evil.example"}).status_code == 403
    assert auth.get("/api/devices", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert auth.get("/api/devices", headers={"Host": "evil.example"}).status_code == 400
    assert auth.get("/api/devices").headers["Cache-Control"] == "no-store"
    assert auth.post("/api/devices", content="x" * 131073).status_code == 413
    assert auth.post("/api/devices", content=iter([b"x" * 70000, b"x" * 70000])).status_code == 413


def test_built_frontend_bootstrap_has_specific_csp_hash(settings):
    import base64
    import hashlib
    from fastapi.testclient import TestClient
    from backend.hcc.main import create_app
    settings.frontend_dir.mkdir()
    script = "console.log('boot')"
    (settings.frontend_dir / "index.html").write_text(f"<html><script>{script}</script></html>")
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
        expected = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        assert response.status_code == 200
        assert "'sha256-" + expected + "'" in response.headers["content-security-policy"]
        assert "script-src 'self' 'unsafe-inline'" not in response.headers["content-security-policy"]


def test_device_crud_real_ssh_stays_disabled(auth):
    response = auth.post("/api/devices", json=DEVICE)
    assert response.status_code == 201
    device = response.json()
    assert device["host"] == "hemu-server.top"
    assert device["snapshot"]["error"]["code"] == "ssh_disabled"
    assert "private_key" not in json.dumps(device)
    ident = device["id"]
    response = auth.put(f"/api/devices/{ident}", json={**DEVICE, "name": "Renamed"})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert auth.delete(f"/api/devices/{ident}").status_code == 200
    assert auth.post(f"/api/devices/{ident}/refresh").status_code == 404


def test_metrics_history_and_demo_labels(auth):
    devices = auth.get("/api/devices").json()
    assert len(devices) == 3
    item = devices[0]
    assert item["mode"] == "demo" and item["snapshot"]["demo"]
    assert 0 <= item["snapshot"]["metrics"]["cpu_percent"] <= 100
    auth.post(f"/api/devices/{item['id']}/refresh")
    history = auth.get(f"/api/devices/{item['id']}/history").json()
    assert len(history) == 2 and history[0]["timestamp"] <= history[1]["timestamp"]


def test_logs_allow_only_discovered_targets_and_filter(auth):
    root = "/api/devices/demo-thinkbook/logs"
    assert auth.get(root, params={"source": "container", "target": "immich-server"}).status_code == 200
    assert auth.get(root, params={"source": "container", "target": "x; touch /tmp/injected"}).status_code == 422
    assert auth.get(root, params={"source": "service", "target": "not-discovered.service"}).status_code == 422
    result = auth.get(root, params={"source": "service", "target": "agent-runner.service", "q": "ERROR"}).json()
    assert result["demo"] and len(result["lines"]) == 1
    assert auth.get(root, params={"limit": 1001}).status_code == 422


def test_backup_restore_atomic_validation_and_audit(auth):
    backup = auth.get("/api/config/backup").json()
    assert "password" not in json.dumps(backup)
    invalid = {"version": 1, "devices": [{**DEVICE, "id":"bad", "jump_device_id":"missing"}]}
    assert auth.post("/api/config/restore", json=invalid).status_code == 422
    assert len(auth.get("/api/devices").json()) == 3
    assert auth.post("/api/config/restore", json=backup).status_code == 200
    assert len(auth.get("/api/devices").json()) == 3
    actions = [item["action"] for item in auth.get("/api/audit").json()]
    assert "config_restored" in actions and "config_exported" in actions


def test_jump_constraints(auth):
    jump = auth.post("/api/devices", json=DEVICE).json()["id"]
    target = auth.post("/api/devices", json={**DEVICE, "name": "NAS", "host": "nas.lan", "jump_device_id":jump}).json()["id"]
    assert auth.delete(f"/api/devices/{jump}").status_code == 409
    assert auth.put(f"/api/devices/{jump}", json={**DEVICE,"jump_device_id":target}).status_code == 422
    assert auth.put(f"/api/devices/{jump}", json={**DEVICE,"mode":"demo"}).status_code == 409
    assert auth.post("/api/devices", json={**DEVICE,"jump_device_id":target}).status_code == 422


@pytest.mark.parametrize("changes", [{"host":"host; touch /tmp/x"}, {"port":0}, {"git_paths":["relative/path"]}, {"health_targets":[{"name":"bad","url":"file:///etc/passwd"}]}, {"health_targets":[{"name":"bad","url":"http://user:pass@host/"}]}])
def test_invalid_configuration(auth, changes):
    assert auth.post("/api/devices", json={**DEVICE, **changes}).status_code == 422


def test_login_throttle_and_logout(client, auth):
    assert auth.post("/api/logout").status_code == 200
    assert auth.get("/api/devices").status_code == 401
    responses = [client.post("/api/login", json={"username":"admin","password":"wrong"}) for _ in range(9)]
    assert responses[-1].status_code == 429


def test_secret_redaction():
    content = "api_key=secret123 password=abc Authorization: Bearer mytoken\n-----BEGIN OPENSSH PRIVATE KEY-----\nprivate\n-----END OPENSSH PRIVATE KEY-----"
    clean = redact(content)
    for secret in ["secret123", "abc", "mytoken", "\nprivate\n"]:
        assert secret not in clean
    assert "[REDACTED]" in clean


def test_removed_demo_devices_are_not_reseeded(auth):
    from backend.hcc.demo import seed
    for device in auth.get("/api/devices").json():
        auth.delete("/api/devices/" + device["id"])
    seed(auth.app.state.db)
    assert auth.get("/api/devices").json() == []
