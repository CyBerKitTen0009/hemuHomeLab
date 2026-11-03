#!/usr/bin/env python3
"""Initialize only this checkout. Never reads existing personal SSH configuration."""
import argparse
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--show-password", action="store_true", help="Display the generated local administrator password")
args = parser.parse_args()
data = ROOT / "data"
data.mkdir(exist_ok=True, mode=0o700)
password = data / "admin.password"
if not password.exists():
    with open(password, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
        file.write(secrets.token_urlsafe(24) + "\n")
    print("已生成 data/admin.password（0600）。")
env = ROOT / ".env"
if not env.exists():
    with open(env, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
        file.write("# Local development only. Production Compose enforces secure cookies.\nHCC_SECURE_COOKIES=false\nHCC_ENABLE_SSH=false\nHCC_SEED_DEMO=true\nHCC_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173\n")
    print("已生成本地 .env；真实 SSH 保持关闭。")
if args.show_password:
    print("管理员：admin\n密码：" + password.read_text().strip())
else:
    print("查看初始密码：python3 scripts/bootstrap.py --show-password")
