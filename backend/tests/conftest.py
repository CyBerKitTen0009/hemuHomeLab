import pytest
from fastapi.testclient import TestClient

from backend.hcc.config import Settings
from backend.hcc.main import create_app

PASSWORD = "test-only-long-password-12345"


@pytest.fixture
def settings(tmp_path):
    password = tmp_path / "password"
    password.write_text(PASSWORD)
    config = tmp_path / "config"
    config.mkdir()
    return Settings(data_dir=tmp_path / "data", config_dir=config, password_file=password, secure_cookies=False, enable_ssh=False, seed_demo=True, origins=["http://testserver"], frontend_dir=tmp_path / "no-frontend", poll_seconds=3600)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def auth(client):
    response = client.post("/api/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client
