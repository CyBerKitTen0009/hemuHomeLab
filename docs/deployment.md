# ThinkBook 常驻部署

2026-11-03 已将控制台部署到 ThinkBook，使用现有 Docker Engine / Compose。Mac 不再承担常驻采集；关闭 Mac 或断开查看连接，ThinkBook 上的服务仍继续采集。当前通过既有 SSH 入口加密访问，控制台只绑定 ThinkBook 的回环地址，没有新增公网端口或修改现有 HTTPS 代理。

## 当前运行实例

- 部署目录：`/home/hemu/apps/homelab-control-center`；源码与 Compose 在 `source/`，运行数据在 `data/`，专用凭据在 `config/`。
- Compose：`source/compose.ssh.yaml`；项目名 `hemu-homelab`，容器 `hemu-homelab-app-1`，镜像 `hemu-hcc:a66342c`。
- ThinkBook 监听：`127.0.0.1:18000`，通过 SSH 转发到浏览器的 `http://localhost:18000`。
- ThinkBook 自采集：`host.docker.internal:22`，通过 Docker 的 `host-gateway` 指向宿主机，使用此前已核验的 ThinkBook 主机密钥；NAS 直连 `192.168.5.100:22`。
- 两台设备的配置和历史已迁移，迁移会话已清除。管理员仍为 `admin`，密码沿用 Mac 上原有管理员密码。
- 凭据与数据目录权限为 0700、私密文件 0600，归容器 UID/GID 10001 所有。密码、私钥和数据库不进入源码仓库或镜像。
- Docker 已启用开机启动，容器为 `restart: unless-stopped`。已验证容器重启后健康检查和两台设备采集恢复，未重启宿主机。

在 Mac 的终端执行：

```sh
sh /Users/apple/HomelabControlCenter/scripts/connect-thinkbook.sh
```

随后打开 [ThinkBook 控制台](http://localhost:18000)。保持该终端运行；Ctrl+C 只断开查看连接。该脚本严格校验专用 `known_hosts`，仅使用指定密钥，不需要本机 Python / Node 后端运行。其他终端需单独配置获准使用的 SSH 密钥与主机信任记录。

此模式的 HTTP 仅存在于浏览器 / SSH 和 Docker 宿主机的本机回环连接之间，跨网络传输由 SSH 加密；因此专用 Compose 中使用非 Secure Cookie，保留 HttpOnly、SameSite、CSRF 和来源校验。此模式不得改成公网 HTTP 绑定。公网直接浏览应使用下文 HTTPS 配置及 Secure Cookie。

在 ThinkBook 上查看状态与日志：

```sh
cd /home/hemu/apps/homelab-control-center/source
docker compose -f compose.ssh.yaml ps
docker compose -f compose.ssh.yaml logs --tail 100 app
```

更新镜像后，设置该目录 `.env` 的 `HCC_IMAGE`，再执行 `docker compose -f compose.ssh.yaml up -d --no-build`。保留父目录的 `data/` 与 `config/`。不要重复覆盖在线数据库；迁移或备份使用 SQLite 在线 backup API，并关闭目标连接、完成 checkpoint 后再传输单个数据库文件。

## 待接入的现有 HTTPS 入口

用户选择沿用现有 HTTPS 入口，尚待补充控制台的最终完整地址。ThinkBook 已有 `digital-life-caddy.service` 在 19443 端口提供 `world.hemu-server.top`，配置为 `/home/hemu/.config/digital-life/caddy/Caddyfile`。目前只检查配置来源和公开证书元数据，没有改变现有代理。现有证书仅覆盖 `world.hemu-server.top` 与其证书列出的 IP；其他域名需要匹配的证书。

已准备 `compose.proxy.yaml` 覆盖配置：保留当前数据、凭据和 `127.0.0.1:18000` 监听，仅将会话改为 Secure Cookie、来源改为必须明确配置的 `HCC_PUBLIC_ORIGIN`。现有代理应为该地址提供有效 HTTPS，并将浏览器的 Host 保留后转发至 `127.0.0.1:18000`。在当前实例的 `.env` 填入实际 HTTPS Origin、完成代理配置后，使用：

```sh
docker compose -f compose.ssh.yaml -f compose.proxy.yaml config --quiet
docker compose -f compose.ssh.yaml -f compose.proxy.yaml up -d --no-build
```

该覆盖配置当前仅验证解析，尚未启用。启用后应使用 HTTPS 地址登录，SSH 转发的 HTTP 地址不再作为浏览器登录入口。

以下为单独使用 Caddy 容器的备用 HTTPS 部署配置。接入已有代理时应复用代理、保留当前数据库，配置真实允许来源与 Secure Cookie；不要直接启用一个新的空数据库实例。

### 证书和 Web 地址

SSH 地址与 Web 控制台地址独立配置。SSH 默认 `hemu-server.top`；Web 必须使用你实际拥有证书且可访问的 HTTPS 域名与自定义端口，例如 `https://console.example.com:8443`。示例域名不是已配置服务。

此方案使用你已有的 TLS 证书，Caddy 不执行 ACME HTTP/TLS 挑战，不要求公网 443，也不自动改 DNS。将匹配 Web 域名的完整证书链和私钥放入：

```text
config/tls/fullchain.pem
config/tls/privkey.pem
```

已有反向代理时，可以由现有代理提供 HTTPS，连接应用内网 8000 端口；不要把未加密 API 直接暴露公网。确保代理保留浏览器 Host 并使用允许的 Web Origin。

### HTTPS 部署前准备

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

### HTTPS 启动

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail 100 app
```

应用没有宿主 Docker socket 挂载，不直接控制宿主 Docker；通过已授权 SSH 账户读取。默认不包含远程写操作。生产会话 Cookie 强制 `Secure`，不能通过 HTTP 登录使用。需要公网访问时使用已有安全网络设施与自定义 HTTPS 端口。

镜像只读根文件系统、无 Linux capabilities、禁止提权；该 HTTPS Compose 使用 `homelab_data` 命名卷，凭据目录只读挂载。切换当前 SSH 实例时需明确迁移数据和凭据挂载，不能直接启动一个空数据库实例。证书私钥不进入镜像。

## 备份与恢复

- 设置页面导出 / 恢复 JSON：仅设备配置，不含凭据；恢复会清空采样，执行前有确认对话框。
- 完整数据：使用 SQLite 在线 backup API，不要直接拷贝正在使用的 SQLite/WAL 文件。
- 容器内完整备份可在数据卷中写入一个新备份文件，再 `docker compose cp` 导出。`scripts/backup.py` 可在宿主机对挂载出来的数据库运行。
- 完整恢复前停止 API；`scripts/backup.py restore ... --confirm-server-stopped` 会清除恢复文件中的登录会话。
- 密钥、已核验主机记录、管理员密码、TLS 私钥独立加密备份，恢复后检查文件所有权与 0600 权限。

ThinkBook 上已完成镜像实际构建与容器运行验证；HTTPS Compose 目前仅验证配置解析，尚未完成证书与公网入口联调。
