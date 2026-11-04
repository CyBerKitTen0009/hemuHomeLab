#!/usr/bin/env python3
"""Install this checkout's configured telemetry client as a user LaunchAgent."""
import argparse
import os
import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "top.hemu.homelab.mac-agent"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--python", type=Path, default=ROOT / "data/mac-agent-venv/bin/python")
args = parser.parse_args()
config = ROOT / "config/mac-agent.json"
if not config.is_file() or config.stat().st_mode & 0o077:
    raise SystemExit("请先创建权限 0600 的 config/mac-agent.json")
if not args.python.is_file():
    raise SystemExit("请先准备带 psutil 的专用 Python 环境")
folder = Path.home() / "Library/LaunchAgents"
folder.mkdir(parents=True, exist_ok=True)
path = folder / (LABEL + ".plist")
plist = {
    "Label": LABEL,
    "ProgramArguments": [str(args.python.absolute()), "-m", "backend.hcc.mac_agent", "--config", str(config), "--log-file", str(ROOT / "data/mac-agent.log")],
    "WorkingDirectory": str(ROOT), "RunAtLoad": True, "KeepAlive": True,
    "ThrottleInterval": 30, "ProcessType": "Background",
    "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONDONTWRITEBYTECODE": "1"},
}
if path.exists() and plistlib.loads(path.read_bytes()).get("WorkingDirectory") != str(ROOT):
    raise SystemExit("已有同名服务来自其他目录，请先检查")
temporary = path.with_suffix(".plist.next")
temporary.write_bytes(plistlib.dumps(plist));temporary.chmod(0o644);os.replace(temporary, path)
domain = "gui/" + str(os.getuid())
subprocess.run(["launchctl", "bootout", domain + "/" + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
print("已安装并启动 Mac 用户登录采集服务：" + LABEL)
