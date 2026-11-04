import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, from_env
from .db import Database
from .demo import seed
from .models import DeviceInput, LoginInput
from .security import COOKIE, create_session, digest, session
from .ssh import ConnectionProblem, SSHCollector


class BackupDevice(DeviceInput):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class ConfigBackup(BaseModel):
    version: int = Field(default=1, ge=1, le=1)
    devices: list[BackupDevice] = Field(max_length=50)


def validate_jump(db, config, device_id=None):
    if config.kind == "windows" and config.mode == "ssh":
        raise HTTPException(422, "第一阶段 SSH 采集仅支持 Linux / NAS")
    if config.jump_device_id:
        jump = db.device(config.jump_device_id)
        if config.jump_device_id == device_id or not jump or jump["mode"] != "ssh" or jump.get("jump_device_id"):
            raise HTTPException(422, "请选择一个已配置的直接 SSH 设备作为跳板，不支持循环或多层跳板")
        if device_id and any(item.get("jump_device_id") == device_id for item in db.devices()):
            raise HTTPException(409, "当前设备已作为跳板，不能再配置上游跳板")


def create_app(settings: Settings | None = None):
    settings = settings or from_env()
    script_hashes = []
    index = settings.frontend_dir / "index.html"
    if index.is_file():
        for script in re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", index.read_text()):
            if script.strip():
                script_hashes.append("'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'")
    script_policy = "'self' " + " ".join(script_hashes)
    locks = defaultdict(asyncio.Lock)
    semaphore = asyncio.Semaphore(3)
    login_attempts = defaultdict(deque)

    async def refresh(app, device):
        async with locks[device["id"]], semaphore:
            try:
                payload = await app.state.collector.collect(device)
            except ConnectionProblem as exc:
                previous = app.state.db.snapshot(device["id"]) or {}
                payload = {**previous, "status": "error", "timestamp": time.time(), "demo": False, "error": {"code": exc.code, "message": exc.message}}
            except Exception:
                payload = {"status": "error", "timestamp": time.time(), "demo": device["mode"] == "demo", "error": {"code": "collector_error", "message": "采集失败，请检查设备配置和服务端运行日志。"}}
            if app.state.db.device(device["id"]) == device:
                app.state.db.save_snapshot(device["id"], payload)
            return payload

    async def poll(app):
        while True:
            await asyncio.sleep(settings.poll_seconds)
            await asyncio.gather(*(refresh(app, device) for device in app.state.db.devices()))

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        app.state.db = Database(settings.data_dir / "homelab.sqlite3")
        salt = os.urandom(16)
        app.state.password_salt = salt
        app.state.password_hash = hashlib.scrypt(settings.password.encode(), salt=salt, n=16384, r=8, p=1)
        app.state.collector = SSHCollector(settings, app.state.db)
        if settings.seed_demo:
            seed(app.state.db)
        await asyncio.gather(*(refresh(app, device) for device in app.state.db.devices()))
        task = asyncio.create_task(poll(app))
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Homelab Control Center", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings

    @app.middleware("http")
    async def request_protection(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            from urllib.parse import urlsplit
            hosts = {urlsplit(origin.strip()).netloc for origin in settings.origins}
            if request.headers.get("host") not in hosts and request.url.path != "/api/health":
                return JSONResponse({"detail": "请求主机未配置在允许列表中"}, 400)
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"detail": "请求来源不在允许列表中"}, 403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "禁止跨站请求"}, 403)
            if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
                try:
                    if int(request.headers.get("content-length", "0")) > 131072:
                        return JSONResponse({"detail": "请求体超过 128 KiB"}, 413)
                except ValueError:
                    return JSONResponse({"detail": "无效请求体长度"}, 400)
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 131072:
                        return JSONResponse({"detail": "请求体超过 128 KiB"}, 413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        response.headers["Content-Security-Policy"] = f"default-src 'self'; script-src {script_policy}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/login")
    async def login(data: LoginInput, request: Request):
        now = time.time()
        # Global and per-peer limits remain effective behind a proxy without trusting X-Forwarded-For.
        ip = request.client.host if request.client else "unknown"
        for key, maximum in [(ip, 8), ("__global__", 100)]:
            attempts = login_attempts[key]
            while attempts and attempts[0] < now - 300:
                attempts.popleft()
            if len(attempts) >= maximum:
                raise HTTPException(429, "登录尝试过多，请 5 分钟后重试", headers={"Retry-After": "300"})
        login_attempts[ip].append(now)
        login_attempts["__global__"].append(now)
        candidate = await asyncio.to_thread(hashlib.scrypt, data.password.encode(), salt=app.state.password_salt, n=16384, r=8, p=1)
        valid_password = hmac.compare_digest(candidate, app.state.password_hash)
        valid_username = hmac.compare_digest(data.username.encode(), settings.username.encode())
        if not (valid_password and valid_username):
            app.state.db.audit("login_failed", "admin")
            raise HTTPException(401, "用户名或密码不正确")
        token, csrf = create_session(app.state.db)
        response = JSONResponse({"username": settings.username, "csrf_token": csrf})
        response.set_cookie(COOKIE, token, max_age=8 * 3600, httponly=True, secure=settings.secure_cookies, samesite="strict", path="/")
        app.state.db.audit("login", "admin")
        return response

    @app.get("/api/session")
    async def current_session(request: Request):
        row = session(request)
        return {"username": settings.username, "csrf_token": row["csrf"], "ssh_enabled": settings.enable_ssh, "read_only": True, "poll_seconds": settings.poll_seconds}

    @app.post("/api/logout")
    async def logout(request: Request):
        session(request, mutation=True)
        with app.state.db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        app.state.db.audit("logout", "admin")
        return response

    def device_or_404(device_id):
        device = app.state.db.device(device_id)
        if not device:
            raise HTTPException(404, "设备不存在")
        return device

    @app.get("/api/devices")
    async def devices(request: Request):
        session(request)
        return [{**device, "snapshot": app.state.db.snapshot(device["id"])} for device in app.state.db.devices()]

    @app.post("/api/devices", status_code=201)
    async def add_device(data: DeviceInput, request: Request):
        session(request, mutation=True)
        if len(app.state.db.devices()) >= 50:
            raise HTTPException(409, "最多配置 50 台设备")
        validate_jump(app.state.db, data)
        device_id = secrets.token_hex(8)
        app.state.db.put_device(device_id, data.model_dump())
        app.state.db.audit("device_added", device_id, data.name)
        device = app.state.db.device(device_id)
        return {**device, "snapshot": await refresh(app, device)}

    @app.put("/api/devices/{device_id}")
    async def update_device(device_id: str, data: DeviceInput, request: Request):
        session(request, mutation=True)
        previous = device_or_404(device_id)
        validate_jump(app.state.db, data, device_id)
        dependents = [item for item in app.state.db.devices() if item.get("jump_device_id") == device_id]
        if dependents and data.mode != "ssh":
            raise HTTPException(409, "此设备仍被用作 SSH 跳板")
        config = data.model_dump()
        connection_fields = ("host", "port", "username", "mode", "credential_ref", "jump_device_id")
        connection_changed = any(previous.get(field) != config.get(field) for field in connection_fields)
        app.state.db.put_device(device_id, config)
        if connection_changed:
            with app.state.db.connect() as conn:
                conn.execute("DELETE FROM snapshots WHERE device_id=?", (device_id,))
                conn.execute("DELETE FROM samples WHERE device_id=?", (device_id,))
        app.state.db.audit("device_updated", device_id, data.name)
        return {**app.state.db.device(device_id), "snapshot": await refresh(app, app.state.db.device(device_id))}

    @app.delete("/api/devices/{device_id}")
    async def delete_device(device_id: str, request: Request):
        session(request, mutation=True)
        device_or_404(device_id)
        if any(item.get("jump_device_id") == device_id for item in app.state.db.devices()):
            raise HTTPException(409, "请先解除其他设备的跳板引用")
        app.state.db.delete_device(device_id)
        app.state.db.audit("device_deleted", device_id)
        return {"ok": True}

    @app.post("/api/devices/{device_id}/refresh")
    async def refresh_device(device_id: str, request: Request):
        session(request, mutation=True)
        device = device_or_404(device_id)
        if locks[device_id].locked():
            raise HTTPException(409, "该设备正在采集，请稍后刷新")
        app.state.db.audit("device_refreshed", device_id)
        return await refresh(app, device)

    @app.get("/api/devices/{device_id}/history")
    async def device_history(device_id: str, request: Request):
        session(request)
        device_or_404(device_id)
        return app.state.db.history(device_id)

    @app.get("/api/devices/{device_id}/logs")
    async def logs(device_id: str, request: Request, source: str = Query(default="system", pattern="^(system|container|service)$"), target: str = Query(default="", max_length=128), limit: int = Query(default=200, ge=1, le=1000), q: str = Query(default="", max_length=200)):
        session(request)
        device = device_or_404(device_id)
        snapshot = app.state.db.snapshot(device_id) or {}
        if source == "container" and target not in {item.get("name") for item in snapshot.get("docker", {}).get("containers", [])}:
            raise HTTPException(422, "请选择已采集到的容器")
        if source == "service" and target not in {item.get("name") for item in snapshot.get("systemd", {}).get("services", [])}:
            raise HTTPException(422, "请选择已采集到的服务")
        try:
            content = await app.state.collector.logs(device, source, target, limit)
        except ConnectionProblem as exc:
            raise HTTPException(502, {"code": exc.code, "message": exc.message})
        lines = content.splitlines()
        if q:
            lines = [line for line in lines if q.casefold() in line.casefold()]
        app.state.db.audit("logs_read", device_id, source + ":" + target)
        return {"lines": lines[-limit:], "demo": device["mode"] == "demo", "limited": True}

    @app.get("/api/audit")
    async def audit(request: Request):
        session(request)
        return app.state.db.audits()

    @app.get("/api/config/backup")
    async def backup(request: Request):
        session(request)
        app.state.db.audit("config_exported")
        return JSONResponse({"version": 1, "devices": app.state.db.devices()}, headers={"Content-Disposition": 'attachment; filename="homelab-config.json"'})

    @app.post("/api/config/restore")
    async def restore(data: ConfigBackup, request: Request):
        session(request, mutation=True)
        configs = {item.id: item for item in data.devices}
        if len(configs) != len(data.devices):
            raise HTTPException(422, "备份中有重复设备 ID")
        for item in data.devices:
            if item.kind == "windows" and item.mode == "ssh":
                raise HTTPException(422, "暂不支持 Windows SSH 采集")
            if item.jump_device_id:
                jump = configs.get(item.jump_device_id)
                if not jump or jump.id == item.id or jump.jump_device_id or jump.mode != "ssh":
                    raise HTTPException(422, "备份中的跳板引用无效")
        async with semaphore:
            with app.state.db.connect() as conn:
                conn.execute("DELETE FROM devices")
                conn.execute("DELETE FROM snapshots")
                conn.execute("DELETE FROM samples")
                for item in data.devices:
                    conn.execute("INSERT INTO devices VALUES (?,?)", (item.id, json.dumps(item.model_dump(exclude={"id"}))))
        app.state.db.audit("config_restored", detail=f"{len(data.devices)} devices")
        return {"ok": True, "devices": len(data.devices)}

    if settings.frontend_dir.is_dir():
        if (settings.frontend_dir / "_app").is_dir():
            app.mount("/_app", StaticFiles(directory=settings.frontend_dir / "_app"), name="assets")

        @app.get("/{path:path}")
        async def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "API 不存在")
            return FileResponse(settings.frontend_dir / "index.html")

    return app


app = create_app()
