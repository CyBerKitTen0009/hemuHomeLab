#!/usr/bin/env python3
"""Enroll this Mac using the administrator password file, without logging secrets."""
import argparse
import http.cookiejar
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--server", required=True)
parser.add_argument("--certificate", type=Path, required=True)
parser.add_argument("--password-file", type=Path, default=ROOT / "data/admin.password")
parser.add_argument("--username", default="admin")
parser.add_argument("--name", default="MacBook Air M3")
parser.add_argument("--repo", type=Path, action="append", default=[], help="Add an explicitly permitted local Git repository")
args = parser.parse_args()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


parts = urlsplit(args.server)
if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
    raise SystemExit("必须使用完整 HTTPS Origin")
config_path = ROOT / "config/mac-agent.json"
previous = {}
if config_path.exists():
    if config_path.stat().st_mode & 0o077:
        raise SystemExit("现有采集配置权限过宽")
    previous = json.loads(config_path.read_text())
    if previous["server"] != args.server.rstrip("/"):
        raise SystemExit("已接入其他控制台，请先检查现有配置")
paths = list(dict.fromkeys(previous.get("allowed_git_paths", []) + [str(p.resolve()) for p in args.repo]))
if len(paths) > 20 or any(not (Path(p) / ".git").exists() or len(p) > 512 for p in paths):
    raise SystemExit("仓库必须存在，最多允许 20 个")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(args.certificate))), NoRedirect())
csrf = None


def call(method, path, payload=None):
    request = urllib.request.Request(args.server.rstrip("/") + path, data=json.dumps(payload).encode() if payload is not None else None, method=method, headers={"Content-Type": "application/json", "Origin": args.server.rstrip("/"), **({"X-CSRF-Token": csrf} if csrf else {})})
    with opener.open(request, timeout=65) as response:
        return json.load(response)


try:
    csrf = call("POST", "/api/login", {"username": args.username, "password": args.password_file.read_text().strip()})["csrf_token"]
    devices = call("GET", "/api/devices")
    device = next((d for d in devices if d["id"] == previous.get("device_id")), None)
    if previous and not device:
        raise SystemExit("原设备已删除，请先备份并移走本机采集配置，再重新接入")
    if device:
        if device["mode"] != "agent" or device["kind"] != "macos":
            raise SystemExit("原设备连接方式已更改，请先检查")
        config = {k: device[k] for k in ["name", "host", "port", "username", "mode", "credential_ref", "jump_device_id", "kind", "git_paths", "health_targets"]}
        config["git_paths"] = list(dict.fromkeys(config["git_paths"] + paths))
        device = call("PUT", "/api/devices/" + device["id"], config)
    else:
        device = call("POST", "/api/devices", {"name": args.name, "host": "macbook-air.local", "kind": "macos", "mode": "agent", "git_paths": paths})
    token = call("POST", "/api/devices/" + device["id"] + "/agent-token")["token"]
    value = {"server": args.server.rstrip("/"), "certificate": str(args.certificate.resolve()), "device_id": device["id"], "token": token, "allowed_git_paths": paths}
    temporary = config_path.with_suffix(".json.next")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(temporary, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(value, file, ensure_ascii=False, indent=2);file.write("\n")
    os.replace(temporary, config_path)
    print("已接入 Mac，允许采集 " + str(len(paths)) + " 个本地 Git 仓库；上报凭据已保存至私密配置。")
except urllib.error.HTTPError as error:
    raise SystemExit("接入请求失败：HTTP " + str(error.code))
finally:
    if csrf:
        try:call("POST", "/api/logout")
        except Exception:pass
