# ThinkBook 常驻部署

2026-11-03 已将控制台部署到 ThinkBook。采集服务由现有 Docker Engine / Compose 常驻运行，Mac 离开家庭网络或关机后仍会采集 ThinkBook 和 NAS。随后按用户选择启用本项目独立的自签名 HTTPS，不申请公网 CA 证书，不使用阿里云 AccessKey，不改变已有 DNS 记录或另一个项目的 19443 服务。

## 当前访问方式

控制台地址：[https://ssh.hemu-server.top:20443](https://ssh.hemu-server.top:20443)。管理员仍为 `admin`，密码沿用原 Mac 实例的管理员密码。

用户需要在浏览器中手动确认自签名证书提示；HTTPS 登录流量仍通过 TLS 加密，会话使用 Secure / HttpOnly / SameSite Cookie。系统没有安装全局信任根或自动绕过浏览器证书警告。自签名实例不发送 HSTS。

公网路由器映射为 **TCP 20443 → 192.168.5.16:20443**，用户已添加映射和 UFW 的 `20443/tcp` 入站规则。公网域名与公网地址的 TLS 1.3、健康接口，以及直接通过公网域名的登录、实时数据与访问防护均已验证；用户已用手机流量确认能看到登录页。

本机存在 Meta 代理路由；原 Docker 桥接发布 HTTPS 端口时，内网正常，但公网连接请求到达物理网卡后无法完成握手。放行 UFW 后仍复现，因此将本项目 HTTPS 容器改为 Linux 主机网络，反向代理到 `127.0.0.1:18000`，公网访问随即恢复。应用容器继续使用原网络与回环端口，既有 19443 项目保持独立。

公开 DNS-over-HTTPS 核查显示根域名 `hemu-server.top` 暂无 A / AAAA 记录，现有 `ssh.hemu-server.top` 已能解析到家庭公网地址，因此复用该记录作为 Web 域名；SSH 仍使用独立的 22222 端口。没有将解析后的公网 IP 固定写入控制台配置。若以后添加根域名解析，还需同步修改下面的 Web Host 与允许来源，不能只更换浏览器地址。

## 实例与配置

- 部署根目录：`/home/hemu/apps/homelab-control-center`；源码位于 `source/`，数据位于 `data/`，SSH / 管理员凭据位于 `config/`，TLS 文件位于 `tls/`。
- Compose 项目名 `hemu-homelab`，使用 `compose.ssh.yaml`、`compose.proxy.yaml`、`compose.public.yaml` 三份配置合并。应用容器 `hemu-homelab-app-1`，HTTPS 容器 `hemu-homelab-https-1`。
- 应用镜像 `hemu-hcc:b395ef1`，HTTPS 镜像 `hemu-hcc-https:selfsigned-20443`。HTTPS 镜像基于官方 Caddy，去掉二进制低端口 file capability，以兼容容器丢弃全部 capabilities 的设置。
- 应用仅发布 `127.0.0.1:18000`；HTTPS 使用 `network_mode: host`，直接监听主机 `0.0.0.0:20443` 并转发到该回环端口。`compose.public.yaml` 用于 Linux 主机部署，HTTPS 不再配置 Docker `ports`。仅启用 HTTP/1.1、HTTP/2，不需要 UDP 映射。
- 应用运行 UID/GID 10001；应用与 HTTPS 均为只读根文件系统、丢弃全部 capabilities、禁止提权，SSH 凭据与 TLS 文件分别只读挂载，不挂载宿主 Docker socket。
- 应用凭据与数据目录 0700、私密文件 0600，归 UID/GID 10001 所有；TLS 目录 0700、证书和私钥 0600，归 HTTPS 容器 UID 0 所有。
- ThinkBook 自采集走 `host.docker.internal:22`，通过 Docker `host-gateway` 访问宿主机；NAS 直接访问 `192.168.5.100:22`。分别严格校验已有主机密钥。
- 两台设备 ID 与历史采样已迁移，迁移会话已清除。Docker 已启用开机启动，容器均设置 `restart: unless-stopped`；已验证应用容器重启后恢复采集，未重启宿主机或其他项目的服务。

当前 `source/.env` 的非秘密配置包括：

```dotenv
HCC_IMAGE=hemu-hcc:b395ef1
HCC_HTTPS_IMAGE=hemu-hcc-https:selfsigned-20443
HCC_CONFIG_PATH=/home/hemu/apps/homelab-control-center/config
HCC_DATA_PATH=/home/hemu/apps/homelab-control-center/data
HCC_TLS_PATH=/home/hemu/apps/homelab-control-center/tls
HCC_PUBLIC_ORIGIN=https://ssh.hemu-server.top:20443
HCC_WEB_HOST=ssh.hemu-server.top
HCC_HTTPS_PORT=20443
HCC_PUBLIC_BIND_ADDRESS=0.0.0.0
HCC_POLL_SECONDS=30
```

`HCC_HTTPS_PORT` 控制 ThinkBook 的监听端口，`HCC_PUBLIC_BIND_ADDRESS` 控制绑定地址，`HCC_HTTP_PORT` 默认 18000，同时用于应用回环发布端口与 HTTPS 上游。`HCC_PUBLIC_ORIGIN` 必须对应浏览器实际使用的完整 HTTPS Origin。如果路由器的外部端口不同，需要相应修改 Origin，而不是假定内外端口相同。

## 已接入的项目监控

2026-11-04 已在 ThinkBook 设备配置中接入：

| 类型 | 目标 | 验证方式 |
| --- | --- | --- |
| Git | `/home/hemu/Projects/digital-life-os` | 只读采集分支、工作区、最近提交 |
| 健康检查 | `http://127.0.0.1:18000/api/health` | Homelab 控制台 API，返回 200 |
| 健康检查 | `http://127.0.0.1:8090/healthz` | Digital Life，返回 200 |

健康请求在 ThinkBook 上执行，使用该机器的回环地址，无需额外公网端口。这里只验证相应 HTTP 接口，不代表完整业务链路或公网入口都正常。没有接入需要管理令牌的接口，也没有改变 Digital Life 的代码或服务配置。

部署源码是 Git 归档，不含 `.git`，因此没有将 `/home/hemu/apps/homelab-control-center/source` 添加为 Git 监控目标。上述配置保存在运行数据库中，凭据仍由服务端私密文件独立管理。

## 证书

专用证书覆盖 `ssh.hemu-server.top`、`hemu-server.top`、ThinkBook 内网 IP 与回环 IP，私钥只在 ThinkBook 生成和保存。证书有效至 **2027-11-03**，不会自动续期；更新证书与私钥后需重启本项目 HTTPS 容器。若以后需要浏览器默认信任与自动续期，可另行改用 DNS 验证签发的证书。

证书 SHA256 指纹：

```text
3F:87:D1:C3:19:8F:66:ED:B9:BF:36:A1:AB:F0:53:AA:19:E0:D7:6E:07:76:12:4A:91:5B:6F:33:E3:92:E8:49
```

## 状态、更新与备份

在 ThinkBook 上：

```sh
cd /home/hemu/apps/homelab-control-center/source
docker compose -f compose.ssh.yaml -f compose.proxy.yaml -f compose.public.yaml ps
docker compose -f compose.ssh.yaml -f compose.proxy.yaml -f compose.public.yaml logs --tail 100 app https
```

构建新镜像后，更新 `.env` 中对应的镜像标签，再用同样三份 Compose 配置执行 `up -d --no-build`。修改 Caddyfile 或更新 TLS 文件后，用同样三份配置执行 `restart https`。保留部署根目录的 `data/`、`config/`、`tls/`，不要重新覆盖在线数据库。

完整备份使用 SQLite 在线 backup API；编辑迁移目标后，关闭数据库连接并完成 checkpoint，再传输单个数据库文件。设置页面导出仅含设备配置，不含凭据；恢复会清空采样。密钥、密码和 TLS 私钥需独立保护，均不进入 Git、构建上下文或镜像。

本次更新前已在宿主机 `data/backups/` 创建完整 SQLite 备份，文件权限 0600，完整性检查为 `ok`。接入后核对两台设备的全部采样数量和最早时间，历史保留；当前尚未配置定时备份。

## SSH-only 应急回退

`compose.ssh.yaml` 单独运行时只绑定回环 HTTP，跨网络传输由既有 SSH 连接加密。它是当前直接 HTTPS 模式的备用方式，不能同时把其 HTTP 端口直接公开。需要回退时，先停止本项目 HTTPS 容器，再以单份 SSH Compose 重建应用：

```sh
docker compose -f compose.ssh.yaml -f compose.proxy.yaml -f compose.public.yaml stop https
docker compose -f compose.ssh.yaml up -d --no-build
```

然后在 Mac 执行 `sh /Users/apple/HomelabControlCenter/scripts/connect-thinkbook.sh`，保持终端运行并访问 `http://localhost:18000`。当前 HTTPS 模式下，该 HTTP 地址不作为浏览器登录入口。

仓库中的独立 `compose.yaml` 为另一套 HTTPS 示例，使用不同的数据卷；不要直接用它替换当前三文件部署，避免启动空数据库。当前既有 `digital-life-caddy.service` 及其 19443 端口属于另一个项目，保持独立。
