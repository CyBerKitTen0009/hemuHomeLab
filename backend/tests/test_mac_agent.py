import json
import ssl
import threading
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from backend.hcc.mac_agent import Reporter, load_config, run
from backend.hcc.mac_probe import permitted_repo


def test_unapproved_repository_is_not_read(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    link = allowed / "escape"
    link.symlink_to(other, target_is_directory=True)
    def forbidden(path):
        pytest.fail("unapproved Git command was executed")
    monkeypatch.setattr("backend.hcc.mac_probe.git_repo", forbidden)
    for path in [other, link]:
        assert "error" in permitted_repo(str(path), [str(allowed)])


def test_config_requires_private_permissions_and_https(tmp_path):
    path = tmp_path / "agent.json"
    config = {"server": "https://lab.example:20443", "device_id": "mac", "token": "t" * 64, "certificate": "cert.pem", "allowed_git_paths": []}
    path.write_text(json.dumps(config));path.chmod(0o600)
    assert load_config(path)["device_id"] == "mac"
    path.chmod(0o644)
    with pytest.raises(ValueError):load_config(path)
    path.chmod(0o600)
    for server in ["http://lab.example", "https://user:pass@lab.example", "https://lab.example/path"]:
        path.write_text(json.dumps({**config, "server": server}))
        with pytest.raises(ValueError):load_config(path)


def test_disconnect_retry_recovers_and_reloads_rotated_credentials(tmp_path, monkeypatch, caplog):
    path = tmp_path / "agent.json"
    first, second = "a" * 64, "b" * 64
    config = {"server": "https://lab.example:20443", "device_id": "mac", "token": first, "certificate": "cert.pem", "allowed_git_paths": []}
    path.write_text(json.dumps(config));path.chmod(0o600)
    used, delays = [], []
    class StopLoop(Exception):pass
    class FakeReporter:
        def __init__(self, current):self.current = current
        def send_once(self):
            used.append(self.current["token"])
            if self.current["token"] == first:raise urllib.error.URLError("network unavailable: " + first)
            return 30
    def sleep(delay):
        delays.append(delay)
        if len(delays) == 1:path.write_text(json.dumps({**config, "token": second}))
        else:raise StopLoop()
    monkeypatch.setattr("backend.hcc.mac_agent.Reporter", FakeReporter)
    monkeypatch.setattr("backend.hcc.mac_agent.time.sleep", sleep)
    monkeypatch.setattr("backend.hcc.mac_agent.os.umask", lambda mode: 0o077)
    with pytest.raises(StopLoop):run(path)
    assert used == [first, second] and delays == [5, 30]
    assert "已上报" in caplog.text and first not in caplog.text and second not in caplog.text


def test_reporter_checks_certificate_and_does_not_forward_credentials_on_redirect(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False).sign(key, hashes.SHA256()))
    certfile = tmp_path / "cert.pem";keyfile = tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()));keyfile.chmod(0o600)
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("Authorization")))
            self.send_response(302)
            self.send_header("Location", "/must-not-receive-token")
            self.end_headers()
        def log_message(self, *args):pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certfile, keyfile)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    try:
        config = {"server": f"https://localhost:{server.server_port}", "device_id": "mac", "token": "test-device-token", "certificate": str(certfile)}
        reporter = Reporter(config)
        with pytest.raises(urllib.error.HTTPError) as error:reporter.request("/config")
        assert error.value.code == 302
        assert seen == [("/api/agents/mac/config", "Bearer test-device-token")]
        # Same self-signed certificate is not accepted without the project trust file.
        reporter.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        with pytest.raises(urllib.error.URLError):reporter.request("/config")
        assert len(seen) == 1
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
