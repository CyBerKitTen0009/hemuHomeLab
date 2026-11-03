import asyncio
import base64
import json
import re
import shlex
from contextlib import asynccontextmanager
from pathlib import Path

import asyncssh

from . import demo
from .security import redact


class ConnectionProblem(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class SSHCollector:
    def __init__(self, settings, db):
        self.settings, self.db = settings, db

    def profile(self, device):
        path = self.settings.config_dir / "credentials.json"
        if not self.settings.enable_ssh:
            raise ConnectionProblem("ssh_disabled", "真实 SSH 尚未启用；请完成凭据配置后设置 HCC_ENABLE_SSH=true。")
        if not path.exists():
            raise ConnectionProblem("credentials_missing", "服务端尚未配置 SSH 凭据，请提供连接信息。")
        if path.stat().st_mode & 0o077:
            raise ConnectionProblem("credential_permissions", "凭据配置文件权限过宽，请在服务端设置为 0600。")
        try:
            profiles = json.loads(path.read_text())
            profile = profiles[device["credential_ref"]]
            key = Path(profile["private_key"]) if profile.get("private_key") else None
            hosts = Path(profile["known_hosts"])
            if (key and not key.is_file()) or not hosts.is_file() or (not key and not profile.get("password")):
                raise KeyError()
        except (ValueError, KeyError, TypeError, OSError):
            raise ConnectionProblem("credentials_missing", "凭据配置不完整：需要专用私钥或密码，以及已核验的 known_hosts 文件。")
        if key and key.stat().st_mode & 0o077:
            raise ConnectionProblem("key_permissions", "私钥文件权限过宽，请在服务端设置为 0600。")
        return {"username": device.get("username") or profile.get("username"), "client_keys": [str(key)] if key else [], "password": profile.get("password"), "known_hosts": str(hosts), "passphrase": profile.get("passphrase"), "agent_path": None, "config": None, "preferred_auth": ["publickey", "password"], "kbdint_auth": False, "connect_timeout": 10, "login_timeout": 10, "keepalive_interval": 15, "keepalive_count_max": 2}

    @asynccontextmanager
    async def connect(self, device):
        options = self.profile(device)
        if not options["username"]:
            raise ConnectionProblem("username_missing", "请配置 SSH 用户名。")
        jump = self.db.device(device["jump_device_id"]) if device.get("jump_device_id") else None
        if device.get("jump_device_id") and (not jump or jump.get("jump_device_id") or jump["mode"] != "ssh"):
            raise ConnectionProblem("invalid_jump", "跳板配置无效，仅支持一个已配置的 SSH 跳板。")
        # New connections resolve DNS each time; do not cache numeric addresses.
        if jump:
            async with asyncssh.connect(jump["host"], port=jump["port"], **self.profile(jump)) as tunnel:
                async with asyncssh.connect(device["host"], port=device["port"], tunnel=tunnel, **options) as conn:
                    yield conn
        else:
            async with asyncssh.connect(device["host"], port=device["port"], **options) as conn:
                yield conn

    async def execute(self, device, command, timeout=50):
        try:
            async with asyncio.timeout(timeout):
                async with self.connect(device) as conn:
                    async with conn.create_process(command, stderr=asyncssh.DEVNULL) as process:
                        chunks, size = [], 0
                        while True:
                            chunk = await process.stdout.read(32768)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > 1048576:
                                raise ConnectionProblem("output_limit", "采集输出超过 1 MiB 上限，请减少仓库或容器数量。")
                            chunks.append(chunk)
                        output = "".join(chunks)
                        await process.wait_closed()
                        if process.exit_status != 0:
                            if re.search(r"permission denied|insufficient permissions|access denied", output, re.IGNORECASE):
                                raise ConnectionProblem("remote_permission_denied", "当前 SSH 用户没有读取所选资源的权限，请在设备端检查该账户的读取权限。")
                            raise ConnectionProblem("remote_command_failed", "远程只读命令执行失败；请检查所需工具是否可用，以及当前账户的读取权限。")
                        return output
        except asyncssh.HostKeyNotVerifiable:
            raise ConnectionProblem("host_key_mismatch", "SSH 主机密钥未知或不匹配。请通过可信渠道核验指纹，再更新专用 known_hosts；程序不会自动信任。")
        except asyncssh.PermissionDenied:
            raise ConnectionProblem("authentication_failed", "SSH 认证失败，请检查用户名和服务端凭据。")
        except (TimeoutError, asyncio.TimeoutError):
            raise ConnectionProblem("timeout", "SSH 连接或采集超时，将在下次轮询重新解析 DNS 并重试。")
        except (OSError, asyncssh.Error):
            raise ConnectionProblem("connection_failed", "无法连接 SSH 主机，请检查域名解析、端口及网络状态。")

    async def collect(self, device):
        if device["mode"] == "demo":
            return demo.snapshot(device)
        config = base64.b64encode(json.dumps({"git_paths": device["git_paths"], "health_targets": device["health_targets"]}).encode()).decode()
        script = "import base64, json\nPROBE_CONFIG = json.loads(base64.b64decode(" + repr(config) + "))\n" + Path(__file__).with_name("remote_probe.py").read_text()
        output = await self.execute(device, "python3 - <<'HCC_READONLY_PROBE'\n" + script + "\nHCC_READONLY_PROBE")
        try:
            payload = json.loads(redact(output))
            if not isinstance(payload, dict) or not isinstance(payload.get("metrics"), dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise ConnectionProblem("invalid_response", "远程采集返回无效数据。")
        import time
        return {**payload, "status": "online", "timestamp": time.time(), "demo": False, "error": None}

    async def logs(self, device, source, target, limit):
        if device["mode"] == "demo":
            return demo.logs(source, target)
        if source == "container":
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", target):
                raise ConnectionProblem("invalid_target", "容器名称无效。")
            command = "docker logs --timestamps --tail " + str(limit) + " " + shlex.quote(target) + " 2>&1"
        elif source == "service":
            if not re.fullmatch(r"[a-zA-Z0-9_@.:-]+\.service", target):
                raise ConnectionProblem("invalid_target", "服务名称无效。")
            command = "journalctl --no-pager --output=short-iso --unit=" + shlex.quote(target) + " -n " + str(limit) + " 2>&1"
        else:
            command = "journalctl --no-pager --output=short-iso -n " + str(limit) + " 2>&1"
        return redact(await self.execute(device, command, timeout=15))
