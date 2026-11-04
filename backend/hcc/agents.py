"""Device-scoped, outbound-only macOS telemetry. No commands or logs channel."""
import hmac
import json
import time
from typing import Annotated

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .security import digest, redact


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Percent = Annotated[float, Field(ge=0, le=100)]
Count = Annotated[int, Field(ge=0, le=2**63 - 1)]
Rate = Annotated[float, Field(ge=0, le=10**15)]


class DiskReport(ReportModel):
    mount: str = Field(min_length=1, max_length=512)
    total: Count
    used: Count
    percent: Percent


class MetricsReport(ReportModel):
    cpu_percent: Percent
    cpu_count: int = Field(ge=1, le=4096)
    memory_percent: Percent
    memory_total: Count
    memory_used: Count
    disk_percent: Percent
    network_rx: Rate
    network_tx: Rate
    load: list[Annotated[float, Field(ge=0, le=10**6)]] = Field(min_length=3, max_length=3)
    uptime: Annotated[float, Field(ge=0, le=10**12)]
    disks: list[DiskReport] = Field(min_length=1, max_length=16)


class GitReport(ReportModel):
    path: str = Field(min_length=1, max_length=512)
    name: str = Field(default="", max_length=256)
    branch: str = Field(default="", max_length=256)
    changes: int = Field(default=0, ge=0, le=10**9)
    dirty: bool = False
    commit: str = Field(default="", max_length=64)
    message: str = Field(default="", max_length=512)
    relative_time: str = Field(default="", max_length=64)
    ahead_behind: str = Field(default="", max_length=64)
    error: str | None = Field(default=None, max_length=256)


class AgentReport(ReportModel):
    hostname: str = Field(min_length=1, max_length=253)
    os: str = Field(min_length=1, max_length=128)
    kernel: str = Field(min_length=1, max_length=128)
    metrics: MetricsReport
    git: list[GitReport] = Field(default_factory=list, max_length=20)


def authorize_agent(request: Request, device_id: str):
    db = request.app.state.db
    device = db.device(device_id)
    header = request.headers.get("authorization", "")
    token = header[7:] if header.startswith("Bearer ") else ""
    with db.connect() as conn:
        row = conn.execute("SELECT token_hash FROM agent_tokens WHERE device_id=?", (device_id,)).fetchone()
    if not token or len(token) > 256 or not row or not device or device["mode"] != "agent" or not hmac.compare_digest(digest(token), row[0]):
        raise HTTPException(401, "上报凭据无效或已撤销")
    return device


def current_snapshot(db, device, poll_seconds):
    previous = db.snapshot(device["id"])
    timeout = max(120, poll_seconds * 4)
    if not previous:
        return {"status": "offline", "timestamp": 0, "demo": False, "error": {"code": "agent_waiting", "message": "等待此设备主动上报。"}}
    if time.time() - previous.get("timestamp", 0) > timeout:
        return {**previous, "status": "offline", "error": {"code": "agent_offline", "message": f"超过 {timeout} 秒未收到上报；设备可能休眠、关机或暂时没有网络。"}}
    return previous


def snapshot_payload(report, device):
    paths = [item.path for item in report.git]
    if len(set(paths)) != len(paths) or any(path not in device["git_paths"] for path in paths):
        raise HTTPException(422, "上报包含未配置或重复的 Git 仓库")
    payload = json.loads(redact(report.model_dump_json()))
    payload.update({
        "status": "online", "timestamp": time.time(), "demo": False, "error": None,
        "docker": {"available": False, "error": "Mac 采集端当前仅提供系统指标与 Git 状态。", "containers": [], "images": [], "compose": []},
        "systemd": {"available": False, "error": "macOS 不使用 systemd。", "services": []},
        "health": [],
    })
    return payload
