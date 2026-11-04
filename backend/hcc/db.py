import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, config TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS agent_tokens (device_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots (device_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY, device_id TEXT NOT NULL, timestamp REAL NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS samples_device_time ON samples(device_id,timestamp);
                CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL);
            """)
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def devices(self):
        with self.connect() as conn:
            return [{"id": row["id"], **json.loads(row["config"])} for row in conn.execute("SELECT * FROM devices ORDER BY rowid")]

    def device(self, device_id):
        return next((item for item in self.devices() if item["id"] == device_id), None)

    def put_device(self, device_id, config):
        with self.connect() as conn:
            conn.execute("INSERT INTO devices VALUES (?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config", (device_id, json.dumps(config)))

    def delete_device(self, device_id):
        with self.connect() as conn:
            for table, column in [("devices", "id"), ("snapshots", "device_id"), ("samples", "device_id"), ("agent_tokens", "device_id")]:
                conn.execute(f"DELETE FROM {table} WHERE {column}=?", (device_id,))

    def snapshot(self, device_id):
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM snapshots WHERE device_id=?", (device_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def save_snapshot(self, device_id, payload):
        with self.connect() as conn:
            conn.execute("INSERT INTO snapshots VALUES (?,?) ON CONFLICT(device_id) DO UPDATE SET payload=excluded.payload", (device_id, json.dumps(payload)))
            if payload.get("metrics") and payload.get("status") == "online":
                conn.execute("INSERT INTO samples(device_id,timestamp,payload) VALUES (?,?,?)", (device_id, payload["timestamp"], json.dumps(payload["metrics"])))
            conn.execute("DELETE FROM samples WHERE timestamp < ?", (time.time() - 86400 * 7,))
            conn.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            conn.execute("DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 10000)")

    def history(self, device_id, limit=120):
        with self.connect() as conn:
            rows = conn.execute("SELECT timestamp,payload FROM samples WHERE device_id=? ORDER BY timestamp DESC LIMIT ?", (device_id, limit)).fetchall()
            return [{"timestamp": row[0], **json.loads(row[1])} for row in reversed(rows)]

    def audit(self, action, target="", detail=""):
        with self.connect() as conn:
            conn.execute("INSERT INTO audit(timestamp,action,target,detail) VALUES (?,?,?,?)", (time.time(), action, target, detail))

    def audits(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")]
