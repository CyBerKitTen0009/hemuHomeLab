import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("HCC_DATA_DIR", str(ROOT / "data"))))
    config_dir: Path = field(default_factory=lambda: Path(os.getenv("HCC_CONFIG_DIR", str(ROOT / "config"))))
    frontend_dir: Path = field(default_factory=lambda: ROOT / "frontend" / "build")
    username: str = field(default_factory=lambda: os.getenv("HCC_ADMIN_USER", "admin"))
    password_file: Path = field(default_factory=lambda: Path(os.getenv("HCC_ADMIN_PASSWORD_FILE", str(ROOT / "data" / "admin.password"))))
    secure_cookies: bool = field(default_factory=lambda: os.getenv("HCC_SECURE_COOKIES", "true").lower() == "true")
    enable_ssh: bool = field(default_factory=lambda: os.getenv("HCC_ENABLE_SSH", "false").lower() == "true")
    seed_demo: bool = field(default_factory=lambda: os.getenv("HCC_SEED_DEMO", "true").lower() == "true")
    poll_seconds: int = field(default_factory=lambda: max(10, int(os.getenv("HCC_POLL_SECONDS", "30"))))
    origins: list[str] = field(default_factory=lambda: os.getenv("HCC_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000").split(","))

    @property
    def password(self) -> str:
        value = self.password_file.read_text().strip() if self.password_file.exists() else ""
        if len(value) < 16:
            raise RuntimeError("请先运行 python3 scripts/bootstrap.py 生成管理员密码（至少 16 字符）。")
        return value


def from_env() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    return Settings()
