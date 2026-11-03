import math
import time

GIB = 1024 ** 3


def seed(db):
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM metadata WHERE key='demo_seeded'").fetchone():
            return
        conn.execute("INSERT INTO metadata VALUES ('demo_seeded','true')")
    if db.devices():
        return
    for ident, name, kind in [("demo-thinkbook", "ThinkBook", "linux"), ("demo-nas", "Storage NAS", "nas"), ("demo-windows", "Windows Desktop", "windows")]:
        db.put_device(ident, {"name": name, "host": "hemu-server.top" if kind == "linux" else "nas.lan" if kind == "nas" else "desktop.lan", "port": 22, "username": "", "mode": "demo", "kind": kind, "credential_ref": "thinkbook", "jump_device_id": None, "git_paths": [], "health_targets": []})


def snapshot(device):
    now = time.time()
    nas = device["kind"] == "nas"
    if device["kind"] == "windows":
        return {"status": "offline", "timestamp": now, "demo": True, "error": {"code": "planned_device", "message": "模拟离线设备；首期真实采集仅支持 Linux / NAS。"}, "metrics": None, "docker": {"available": False, "containers": [], "images": [], "compose": []}, "systemd": {"available": False, "services": []}, "git": [], "health": []}
    cpu = round((12 if nas else 24) + 8 * math.sin(now / 23), 1)
    memory = 36.8 if nas else 48.2
    containers = [{"id": (str(index) * 64)[:64], "name": name, "image": image, "state": state, "status": "Up 6 days (healthy)" if state == "running" else "Exited (1) 2 hours ago", "ports": ports, "cpu": f"{load}%", "memory": ram} for index, (name, image, state, ports, load, ram) in enumerate([("immich-server", "ghcr.io/immich-app/immich-server:v2", "running", "2283/tcp", 2.4, "428 MiB / 16 GiB"), ("postgres", "postgres:16-alpine", "running", "5432/tcp", 0.4, "168 MiB / 16 GiB"), ("grafana", "grafana/grafana:12", "running", "3000/tcp", 0.2, "86 MiB / 16 GiB"), ("agent-worker", "homelab/agent:local", "exited", "—", 0, "0 B / 16 GiB")], 1)]
    return {"status": "online", "timestamp": now, "demo": True, "error": None, "hostname": "fnos-nas" if nas else "thinkbook-omarchy", "os": "飞牛 fnOS" if nas else "Omarchy · Arch Linux", "kernel": "6.12.21-lts", "metrics": {"cpu_percent": cpu, "cpu_count": 4 if nas else 16, "memory_percent": memory, "memory_total": 16 * GIB, "memory_used": int(16 * GIB * memory / 100), "disk_percent": 62.4 if nas else 38.6, "disks": [{"mount": "/", "total": (4000 if nas else 512) * GIB, "used": (2496 if nas else 197.6) * GIB, "percent": 62.4 if nas else 38.6}], "network_rx": int(1240000 + 400000 * math.sin(now / 11)), "network_tx": int(280000 + 90000 * math.sin(now / 17)), "load": [0.42, 0.58, 0.64], "uptime": 86400 * 12 + 3600 * 7}, "docker": {"available": True, "error": None, "containers": containers[:3] if nas else containers, "images": [{"Repository": item["image"].rsplit(":", 1)[0], "Tag": item["image"].rsplit(":", 1)[-1], "ID": "demo-image-" + str(index), "Size": size} for index, (item, size) in enumerate(zip(containers, ["1.2 GB", "271 MB", "472 MB", "198 MB"]))], "compose": [{"Name": "media-stack", "Status": "running(2)", "ConfigFiles": "/srv/compose/media/compose.yml"}, {"Name": "observability", "Status": "running(1)", "ConfigFiles": "/srv/compose/monitoring/compose.yml"}]}, "systemd": {"available": True, "error": None, "services": [{"name": name, "description": description, "active": active, "sub": sub, "load": "loaded"} for name, description, active, sub in [("docker.service", "Docker Application Container Engine", "active", "running"), ("sshd.service", "OpenSSH Daemon", "active", "running"), ("agent-runner.service", "Personal AI agent scheduler", "failed", "failed"), ("systemd-journald.service", "Journal Service", "active", "running")]]}, "git": [{"path": "/srv/projects/homelab", "name": "homelab", "branch": "main", "changes": 0, "dirty": False, "commit": "8f21c9a", "message": "chore: update compose services", "relative_time": "2 hours ago", "ahead_behind": "0\t0"}, {"path": "/srv/projects/agent-workspace", "name": "agent-workspace", "branch": "feat/memory", "changes": 3, "dirty": True, "commit": "c4e9d12", "message": "feat: add persistent agent memory", "relative_time": "38 minutes ago", "ahead_behind": "2\t0"}], "health": [{"name": "Immich", "url": "http://localhost:2283", "status": "healthy", "code": 200, "latency_ms": 24}, {"name": "Grafana", "url": "http://localhost:3000/api/health", "status": "healthy", "code": 200, "latency_ms": 12}, {"name": "Agent API", "url": "http://localhost:8081/health", "status": "unhealthy", "code": 503, "latency_ms": 210}]}


def logs(source, target):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if source == "service" and target == "agent-runner.service":
        return "\n".join([f"{timestamp} thinkbook systemd[1]: Starting Personal AI agent scheduler...", f"{timestamp} agent-runner[1203]: INFO Loading workspace configuration", f"{timestamp} agent-runner[1203]: ERROR upstream connection refused (retry 3/3)", f"{timestamp} systemd[1]: agent-runner.service: Main process exited, status=1/FAILURE", f"{timestamp} systemd[1]: agent-runner.service: Failed with result 'exit-code'."])
    return "\n".join(f"{timestamp} {target or 'system'} [{level}] {message}" for level, message in [("INFO", "Service started successfully"), ("INFO", "Connection pool initialized"), ("DEBUG", "Health check completed in 12ms"), ("INFO", "Scheduled task completed"), ("WARN", "Request exceeded 200ms threshold"), ("INFO", "Ready to accept connections")])
