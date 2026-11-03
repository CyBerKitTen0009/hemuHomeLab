#!/usr/bin/env python3
"""Online SQLite backup or explicit offline restore. Credentials are never archived."""
import argparse
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["backup", "restore"])
parser.add_argument("file", type=Path)
parser.add_argument("--database", type=Path, default=ROOT / "data" / "homelab.sqlite3")
parser.add_argument("--confirm-server-stopped", action="store_true")
args = parser.parse_args()
os.umask(0o077)
if args.action == "restore" and not args.confirm_server_stopped:
    parser.error("恢复前请停止 API，然后传入 --confirm-server-stopped")
source = args.database if args.action == "backup" else args.file
target = args.file if args.action == "backup" else args.database
if not source.is_file():
    parser.error("源数据库不存在")
if source.resolve() == target.resolve():
    parser.error("源和目标不能相同")
if args.action == "backup" and target.exists():
    parser.error("备份目标已存在，请使用新文件名")
target.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
    if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        parser.error("源数据库完整性检查失败")
    with sqlite3.connect(target) as dst:
        src.backup(dst)
        dst.execute("DELETE FROM sessions")
target.chmod(0o600)
print("已完成：" + str(target))
