"""Executed on a managed Linux host using its existing Python 3. No installs or writes."""
import concurrent.futures
import json
import os
import platform
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def run(argv, timeout=5):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout, env={**os.environ, "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
        return result.returncode, result.stdout[:262144], result.stderr[:1000]
    except FileNotFoundError:
        return 127, "", "command not installed"
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"


def cpu_sample():
    values = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:9]))
    return sum(values), values[3] + values[4]


def net_sample():
    received = sent = 0
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        interface, values = line.split(":", 1)
        if interface.strip() == "lo" or interface.strip().startswith(("veth", "docker", "br-")):
            continue
        fields = values.split()
        received += int(fields[0])
        sent += int(fields[8])
    return received, sent


def metrics():
    before_cpu, before_net, before_time = cpu_sample(), net_sample(), time.monotonic()
    time.sleep(0.25)
    after_cpu, after_net = cpu_sample(), net_sample()
    elapsed = time.monotonic() - before_time
    total = after_cpu[0] - before_cpu[0]
    cpu = 100 * (1 - (after_cpu[1] - before_cpu[1]) / total) if total else 0
    mem = {line.split(":")[0]: int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines() if len(line.split()) > 1 and line.split()[1].isdigit()}
    mounts, disks = set(), []
    for line in Path("/proc/mounts").read_text().splitlines():
        fields = line.split()
        source, mount, fs = fields[:3]
        mount = mount.replace("\\040", " ")
        if fs not in {"ext4", "ext3", "btrfs", "xfs", "zfs", "vfat", "overlay"} or source in mounts or (fs == "overlay" and mount != "/"):
            continue
        try:
            disk = shutil.disk_usage(mount)
            disks.append({"mount": mount, "total": disk.total, "used": disk.used, "percent": round(disk.used / disk.total * 100, 1)})
            mounts.add(source)
        except OSError:
            pass
    if not disks:
        disk = shutil.disk_usage("/")
        disks.append({"mount": "/", "total": disk.total, "used": disk.used, "percent": round(disk.used / disk.total * 100, 1)})
    return {"cpu_percent": round(max(0, min(100, cpu)), 1), "cpu_count": os.cpu_count(), "memory_total": mem["MemTotal"], "memory_used": mem["MemTotal"] - mem.get("MemAvailable", mem.get("MemFree", 0)), "memory_percent": round((1 - mem.get("MemAvailable", mem.get("MemFree", 0)) / mem["MemTotal"]) * 100, 1), "disk_percent": disks[0]["percent"], "disks": disks, "network_rx": round(max(0, after_net[0] - before_net[0]) / elapsed), "network_tx": round(max(0, after_net[1] - before_net[1]) / elapsed), "load": list(os.getloadavg()), "uptime": float(Path("/proc/uptime").read_text().split()[0])}


def json_lines(text):
    rows = []
    for line in text.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def docker():
    code, output, error = run(["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"])
    if code:
        return {"available": False, "error": "Docker 未安装" if code == 127 else "无 Docker 读取权限或守护进程未运行", "containers": [], "images": [], "compose": []}
    _, stats, _ = run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=8)
    usage = {item.get("Name"): item for item in json_lines(stats)}
    containers = [{"id": row.get("ID"), "name": row.get("Names"), "image": row.get("Image"), "state": row.get("State"), "status": row.get("Status"), "ports": row.get("Ports"), "cpu": usage.get(row.get("Names"), {}).get("CPUPerc", "—"), "memory": usage.get(row.get("Names"), {}).get("MemUsage", "—")} for row in json_lines(output)]
    _, image_text, _ = run(["docker", "images", "--format", "{{json .}}"])
    compose_code, compose_text, _ = run(["docker", "compose", "ls", "--all", "--format", "json"])
    try:
        projects = json.loads(compose_text) if compose_code == 0 else []
    except ValueError:
        projects = []
    return {"available": True, "error": None, "containers": containers[:200], "images": json_lines(image_text)[:200], "compose": projects[:100]}


def systemd():
    code, output, _ = run(["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--output=json"])
    if code:
        return {"available": False, "error": "systemd 不可用或当前用户无读取权限", "services": []}
    try:
        rows = json.loads(output)
    except ValueError:
        return {"available": False, "error": "当前 systemd 不支持 JSON 输出", "services": []}
    return {"available": True, "error": None, "services": [{"name": row["unit"], "description": row.get("description", ""), "active": row.get("active", "unknown"), "sub": row.get("sub", "unknown"), "load": row.get("load", "unknown")} for row in rows][:300]}


def git_repo(path):
    git = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", path]
    code, branch, error = run([*git, "branch", "--show-current"])
    if code:
        return {"path": path, "error": "仓库不存在、非 Git 仓库或无读取权限"}
    _, status, _ = run([*git, "status", "--porcelain=v1", "--untracked-files=normal"])
    _, commit, _ = run([*git, "log", "-1", "--format=%h%x1f%s%x1f%ar"])
    fields = commit.strip().split("\x1f")
    _, ahead, _ = run([*git, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"])
    return {"path": path, "name": Path(path).name, "branch": branch.strip() or "detached HEAD", "changes": len(status.splitlines()), "dirty": bool(status.strip()), "commit": fields[0] if fields else "", "message": fields[1] if len(fields) > 1 else "暂无提交", "relative_time": fields[2] if len(fields) > 2 else "", "ahead_behind": ahead.strip()}


def health_check(target):
    started = time.monotonic()
    try:
        # Disable inherited proxies; each check runs on the managed device.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(target["url"], headers={"User-Agent": "HomelabControlCenter/0.1"})
        with opener.open(request, timeout=3) as response:
            code = response.status
        return {**target, "status": "healthy" if 200 <= code < 400 else "unhealthy", "code": code, "latency_ms": round((time.monotonic() - started) * 1000)}
    except urllib.error.HTTPError as exc:
        return {**target, "status": "healthy" if 300 <= exc.code < 400 else "unhealthy", "code": exc.code, "latency_ms": round((time.monotonic() - started) * 1000)}
    except Exception:
        return {**target, "status": "unhealthy", "code": None, "latency_ms": None, "error": "连接失败、超时或 TLS 校验失败"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def collect(config):
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tasks = {"metrics": pool.submit(metrics), "docker": pool.submit(docker), "systemd": pool.submit(systemd)}
        repos = [pool.submit(git_repo, path) for path in config.get("git_paths", [])]
        checks = [pool.submit(health_check, target) for target in config.get("health_targets", [])]
        payload = {name: task.result() for name, task in tasks.items()}
        payload.update({"git": [task.result() for task in repos], "health": [task.result() for task in checks]})
    payload.update({"hostname": socket.gethostname(), "os": platform.freedesktop_os_release().get("PRETTY_NAME", platform.system()), "kernel": platform.release()})
    return payload


if __name__ == "__main__":
    print(json.dumps(collect(PROBE_CONFIG)))
