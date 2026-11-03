# Docker Compose 与自定义 HTTPS 端口

先在 Mac 验证，再准备部署 ThinkBook。已完成通过 SSH 读取 ThinkBook 的实际指标和日志；该文档描述后续部署方案，尚未向家庭主机安装或部署控制台，也未修改网络配置。

## 证书和 Web 地址

SSH 地址与 Web 控制台地址独立配置。SSH 默认 `hemu-server.top`；Web 必须使用你实际拥有证书且可访问的 HTTPS 域名与自定义端口，例如 `https://console.example.com:8443`。示例域名不是已配置服务。

此方案使用你已有的 TLS 证书，Caddy 不执行 ACME HTTP/TLS 挑战，不要求公网 443，也不自动改 DNS。将匹配 Web 域名的完整证书链和私钥放入：

```text
config/tls/fullchain.pem
config/tls/privkey.pem
```

已有反向代理时，可以由现有代理提供 HTTPS，连接应用内网 8000 端口；不要把未加密 API 直接暴露公网。确保代理保留浏览器 Host 并使用允许的 Web Origin。

## 部署前准备

1. 确认已有 Docker Engine、Compose 和符合要求的 TLS 证书。
2. 准备 `config/admin.password`（随机 24+ 字符，0600）。镜像以 UID/GID 10001 运行，该文件与专用 SSH 凭据必须对此 UID 可读。
3. 准备 `config/credentials.json` 与专用私钥 / known_hosts。容器内路径应使用挂载后的 `/run/hcc/...`，不要照搬 Mac 上的绝对路径。
4. 设置 `.env` 中 `HCC_PUBLIC_ORIGIN` 为实际 Web HTTPS Origin，包含自定义端口。初期可保留 `HCC_ENABLE_SSH=false`。
5. 默认 `HCC_BIND_ADDRESS=127.0.0.1` 仅本机访问。向已有内网反向代理提供服务时，绑定地址按实际网络规划设置。若需要对公网开放，先单独确认路由器映射、绑定地址与访问策略；本项目不会自动更改这些设置。

配置示例：

```dotenv
HCC_ADMIN_USER=admin
HCC_PUBLIC_ORIGIN=https://YOUR_WEB_HOST:ACTUAL_HTTPS_PORT
HCC_HTTPS_PORT=8443
HCC_BIND_ADDRESS=127.0.0.1
HCC_ENABLE_SSH=false
HCC_SEED_DEMO=false
HCC_POLL_SECONDS=30
```

`HCC_HTTPS_PORT` 是宿主机映射端口，容器内 Caddy 固定监听 8443。Web Origin 应写浏览器最终看到的外部端口。

## 经授权后启动

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail 100 app
```

应用没有宿主 Docker socket 挂载，不直接控制宿主 Docker；通过已授权 SSH 账户读取。默认不包含远程写操作。生产会话 Cookie 强制 `Secure`，不能通过 HTTP 登录使用。需要公网访问时使用已有安全网络设施与自定义 HTTPS 端口。

镜像只读根文件系统、无 Linux capabilities、禁止提权；SQLite 在 `homelab_data` 命名卷，凭据目录只读挂载。证书私钥不进入镜像。

## 备份与恢复

- 设置页面导出 / 恢复 JSON：仅设备配置，不含凭据；恢复会清空采样，执行前有确认对话框。
- 完整数据：使用 SQLite 在线 backup API，不要直接拷贝正在使用的 SQLite/WAL 文件。
- 容器内完整备份可在数据卷中写入一个新备份文件，再 `docker compose cp` 导出。`scripts/backup.py` 可在宿主机对挂载出来的数据库运行。
- 完整恢复前停止 API；`scripts/backup.py restore ... --confirm-server-stopped` 会清除恢复文件中的登录会话。
- 密钥、已核验主机记录、管理员密码、TLS 私钥独立加密备份，恢复后检查文件所有权与 0600 权限。

Docker 引擎当前未运行，因此此轮仅验证 Compose 配置解析，未完成镜像构建或容器 HTTPS 联调。
