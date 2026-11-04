"""Read only system counters and explicitly permitted Git metadata on this Mac."""
import concurrent.futures
import os
import platform
import shutil
import socket
import time
from pathlib import Path

import psutil

from .remote_probe import git_repo


def network_totals():
    counters = psutil.net_io_counters(pernic=True)
    # Count physical adapters rather than also counting the same traffic in VPNs.
    rows = [row for name, row in counters.items() if name.startswith("en")]
    return sum(row.bytes_recv for row in rows), sum(row.bytes_sent for row in rows)


def metrics():
    before, start = network_totals(), time.monotonic()
    cpu = psutil.cpu_percent(interval=0.25)
    after, elapsed = network_totals(), time.monotonic() - start
    memory = psutil.virtual_memory()
    # APFS's writable Data volume reflects the space used by applications/data.
    mount = "/System/Volumes/Data" if Path("/System/Volumes/Data").is_dir() else "/"
    disk = shutil.disk_usage(mount)
    percent = round(disk.used / disk.total * 100, 1)
    return {
        "cpu_percent": cpu, "cpu_count": psutil.cpu_count() or 1,
        "memory_percent": memory.percent, "memory_total": memory.total,
        "memory_used": memory.total - memory.available,
        "disk_percent": percent,
        "disks": [{"mount": mount, "total": disk.total, "used": disk.used, "percent": percent}],
        "network_rx": max(0, (after[0] - before[0]) / elapsed),
        "network_tx": max(0, (after[1] - before[1]) / elapsed),
        "load": list(os.getloadavg()), "uptime": max(0, time.time() - psutil.boot_time()),
    }


def permitted_repo(path, allowed_paths):
    resolved = Path(path).resolve()
    if resolved not in {Path(item).resolve() for item in allowed_paths}:
        return {"path": path, "name": Path(path).name, "error": "该仓库尚未在此 Mac 的本机允许列表中配置"}
    result = git_repo(str(resolved))
    result.update(path=path, name=Path(path).name)
    for field, limit in {"name": 256, "branch": 256, "commit": 64, "message": 512, "relative_time": 64, "ahead_behind": 64, "error": 256}.items():
        if field in result and isinstance(result[field], str):
            result[field] = result[field][:limit]
    return result


def collect(paths, allowed_paths):
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        metric_task = pool.submit(metrics)
        repos = list(pool.map(lambda path: permitted_repo(path, allowed_paths), paths))
        values = metric_task.result()
    return {"hostname": socket.gethostname(), "os": "macOS " + platform.mac_ver()[0], "kernel": platform.release(), "metrics": values, "git": repos}
