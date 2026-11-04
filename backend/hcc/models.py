import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class HealthTarget(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    url: str = Field(max_length=512)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError("仅支持无凭据的 HTTP / HTTPS 地址")
        try:
            port = parts.port
            if port is not None and not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            raise ValueError("端口无效")
        # These checks run on the selected managed device, never on the API host.
        if parts.hostname in {"169.254.169.254", "metadata.google.internal"}:
            raise ValueError("不允许云平台元数据地址")
        return value


class DeviceInput(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(default="hemu-server.top", min_length=1, max_length=253)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_.-]*$")
    mode: Literal["demo", "ssh", "agent"] = "ssh"
    credential_ref: str = Field(default="thinkbook", pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    jump_device_id: str | None = Field(default=None, max_length=64)
    kind: Literal["linux", "nas", "windows", "macos"] = "linux"
    git_paths: list[str] = Field(default_factory=list, max_length=20)
    health_targets: list[HealthTarget] = Field(default_factory=list, max_length=12)

    @field_validator("host")
    @classmethod
    def valid_host(cls, value: str) -> str:
        try:
            ipaddress.ip_address(value)
        except ValueError:
            if not re.fullmatch(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
                raise ValueError("主机必须为域名或 IP 地址")
        return value

    @field_validator("git_paths")
    @classmethod
    def valid_paths(cls, values: list[str]) -> list[str]:
        if any(not value.startswith("/") or len(value) > 512 or "\x00" in value or "\n" in value for value in values):
            raise ValueError("Git 路径必须为绝对路径，每个路径单独一行")
        return list(dict.fromkeys(values))


class LoginInput(BaseModel):
    username: str = Field(max_length=128)
    password: str = Field(max_length=1024)
