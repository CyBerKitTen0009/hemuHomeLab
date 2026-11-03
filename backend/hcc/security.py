import hashlib
import hmac
import re
import secrets
import time

from fastapi import HTTPException, Request

COOKIE = "hcc_session"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def session(request: Request, mutation=False):
    token = request.cookies.get(COOKIE, "")
    with request.app.state.db.connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE token_hash=? AND expires>?", (digest(token), time.time())).fetchone()
    if not row:
        raise HTTPException(401, "请先登录，或会话已过期")
    if mutation and not hmac.compare_digest(request.headers.get("x-csrf-token", ""), row["csrf"]):
        raise HTTPException(403, "请求验证失败，请刷新后重试")
    return row


def create_session(db):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), csrf, time.time() + 8 * 3600))
    return token, csrf


def redact(value: str) -> str:
    value = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", value)
    value = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)((?:password|passwd|secret|api[_-]?key|access[_-]?token|token)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    return value
