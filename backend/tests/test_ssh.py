import json

import asyncssh
import pytest

from backend.hcc.db import Database
from backend.hcc.ssh import ConnectionProblem, SSHCollector


class TestSSHServer(asyncssh.SSHServer):
    __test__ = False

    def __init__(self, key):
        self.key = key

    def begin_auth(self, username):
        return True

    def public_key_auth_supported(self):
        return True

    def validate_public_key(self, username, key):
        return username == "monitor" and key == self.key


async def test_actual_ssh_key_verification_and_readonly_probe(settings, tmp_path):
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    key_path = tmp_path / "monitor_key"
    client_key.write_private_key(key_path)
    key_path.chmod(0o600)
    commands = []

    async def process_handler(process):
        commands.append(process.command)
        # Deliberately chunk the payload to verify complete stream reads.
        payload = json.dumps({"metrics":{"cpu_percent":12.5}, "docker":{"containers":[]}, "hostname":"test-linux"})
        process.stdout.write(payload[:20])
        import asyncio
        await asyncio.sleep(0.01)
        process.stdout.write(payload[20:])
        process.exit(0)

    async with asyncssh.listen("127.0.0.1", 0, server_factory=lambda: TestSSHServer(client_key.convert_to_public()), server_host_keys=[host_key], process_factory=process_handler) as listener:
        port = listener.get_port()
        hosts = tmp_path / "known_hosts"
        hosts.write_text(f"[127.0.0.1]:{port} " + host_key.export_public_key().decode())
        (settings.config_dir / "credentials.json").write_text(json.dumps({"thinkbook":{"username":"monitor","private_key":str(key_path),"known_hosts":str(hosts)}}))
        (settings.config_dir / "credentials.json").chmod(0o600)
        settings.enable_ssh = True
        collector = SSHCollector(settings, Database(settings.data_dir / "test.sqlite3"))
        device = {"id":"test","host":"127.0.0.1","port":port,"username":"monitor","credential_ref":"thinkbook","jump_device_id":None,"mode":"ssh","git_paths":["/srv/path with ' quote"],"health_targets":[]}
        snapshot = await collector.collect(device)
        assert snapshot["status"] == "online" and snapshot["demo"] is False
        assert snapshot["metrics"]["cpu_percent"] == 12.5
        assert commands[0].startswith("python3 - <<'HCC_READONLY_PROBE'")
        assert "PROBE_CONFIG = json.loads(base64.b64decode(" in commands[0]
        assert "/srv/path with ' quote" not in commands[0]
        wrong_host = asyncssh.generate_private_key("ssh-ed25519")
        hosts.write_text(f"[127.0.0.1]:{port} " + wrong_host.export_public_key().decode())
        with pytest.raises(ConnectionProblem) as error:
            await collector.collect(device)
        assert error.value.code == "host_key_mismatch"
        assert len(commands) == 1  # No command reached the untrusted host.


def test_missing_credentials_and_permission_failures(settings, tmp_path):
    collector = SSHCollector(settings, Database(settings.data_dir / "test.sqlite3"))
    with pytest.raises(ConnectionProblem) as error:
        collector.profile({"credential_ref":"thinkbook"})
    assert error.value.code == "ssh_disabled"
    settings.enable_ssh = True
    with pytest.raises(ConnectionProblem) as error:
        collector.profile({"credential_ref":"thinkbook"})
    assert error.value.code == "credentials_missing"


def test_password_profile_is_server_only_and_requires_private_permissions(settings, tmp_path):
    settings.enable_ssh = True
    hosts = tmp_path / "known_hosts"
    hosts.write_text("")
    profile_file = settings.config_dir / "credentials.json"
    profile_file.write_text(json.dumps({"thinkbook":{"username":"monitor","password":"test-password","known_hosts":str(hosts)}}))
    profile_file.chmod(0o644)
    collector = SSHCollector(settings, Database(settings.data_dir / "test.sqlite3"))
    with pytest.raises(ConnectionProblem) as error:
        collector.profile({"credential_ref":"thinkbook"})
    assert error.value.code == "credential_permissions"
    profile_file.chmod(0o600)
    options = collector.profile({"credential_ref":"thinkbook"})
    assert options["password"] == "test-password" and options["client_keys"] == []
    assert options["agent_path"] is None and options["config"] is None
