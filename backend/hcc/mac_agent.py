"""Outbound HTTPS telemetry client. Never opens a port or runs server commands."""
import argparse
import json
import logging
import logging.handlers
import os
import re
import ssl
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .mac_probe import collect


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_config(path):
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Mac 采集配置权限必须为 0600 或更严格")
    data = json.loads(path.read_text())
    origin = urlsplit(data["server"])
    if origin.scheme != "https" or not origin.hostname or origin.username or origin.password or origin.path not in ("", "/") or origin.query or origin.fragment:
        raise ValueError("上报地址必须为不含凭据的 HTTPS Origin")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", data["device_id"]) or not 32 <= len(data["token"]) <= 256:
        raise ValueError("无效的设备标识或上报凭据")
    paths = data["allowed_git_paths"]
    if len(paths) > 20 or any(not isinstance(p, str) or not p.startswith("/") or len(p) > 512 for p in paths):
        raise ValueError("本机 Git 允许列表无效")
    data["server"] = data["server"].rstrip("/")
    return data


class Reporter:
    def __init__(self, config):
        self.config = config
        context = ssl.create_default_context(cafile=config["certificate"])
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context), NoRedirect())
        self.base = config["server"] + "/api/agents/" + config["device_id"]

    def request(self, path, payload=None):
        body = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        if body is not None and len(body) > 131072:
            raise ValueError("采集结果超过 128 KiB")
        request = urllib.request.Request(self.base + path, data=body, headers={"Authorization": "Bearer " + self.config["token"], "Content-Type": "application/json", "User-Agent": "HomelabMacAgent/0.1"})
        with self.opener.open(request, timeout=15) as response:
            raw = response.read(131073)
            if len(raw) > 131072:
                raise ValueError("服务端响应超过 128 KiB")
            return json.loads(raw)

    def send_once(self):
        settings = self.request("/config")
        paths = settings["git_paths"]
        if not isinstance(paths, list) or len(paths) > 20 or any(not isinstance(p, str) or not p.startswith("/") or len(p) > 512 for p in paths):
            raise ValueError("服务端仓库配置无效")
        payload = collect(paths, self.config["allowed_git_paths"])
        result = self.request("/snapshot", payload)
        return max(10, min(300, int(result["poll_seconds"])))


def run(config_path, once=False, log_file=None):
    os.umask(0o077)
    logger = logging.getLogger("homelab-mac-agent")
    logger.setLevel(logging.INFO)
    if log_file:
        log_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        log_file.touch(mode=0o600, exist_ok=True)
        log_file.chmod(0o600)
        handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1048576, backupCount=2)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    failures, previous_state = 0, None
    while True:
        try:
            # Re-read on retries so certificate/token rotation needs no reinstall.
            reporter = Reporter(load_config(config_path))
            delay = reporter.send_once()
            failures = 0
            if previous_state != "online":
                logger.info("系统指标与 Git 状态已上报")
            previous_state = "online"
            if once:
                return
        except Exception as exc:
            if once:
                raise SystemExit("上报失败：" + type(exc).__name__)
            failures += 1
            delay = min(60, 5 * 2 ** min(failures - 1, 4))
            # No response body, token, Git data or personal logs in diagnostics.
            state = "HTTP " + str(exc.code) if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
            if state != previous_state:
                logger.warning("暂时无法上报（%s），稍后自动重试", state)
            previous_state = state
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-file", type=Path)
    args = parser.parse_args()
    run(args.config, args.once, args.log_file)


if __name__ == "__main__":
    main()
