# Homelab Control Center

面向个人 Homelab 的可运行 Web 控制台。SvelteKit 3 / Svelte 5 / TypeScript 前端，FastAPI / AsyncSSH 后端，SQLite 存储，默认深色主题，支持手机布局。

已确认的第一阶段范围：**只读监控，先在 Mac 本地验证，内置单管理员登录**。2026-11-03 已使用用户提供的专用密钥连接 ThinkBook，完成真实系统指标、Docker、systemd 与日志验证；主机密钥来自本机已存在的精确主机 / 端口信任记录。未安装远程软件或改变 DNS、SSH、路由器、防火墙、代理配置。

随后通过家庭内网直连飞牛 NAS，使用服务端密码认证；本机现有两台真实设备。NAS 的系统指标、磁盘与 systemd 服务列表已验证，当前账户无权读取 Docker 和 journal，页面按受限状态处理。家庭内网地址要求控制台后端能访问该网段。

项目私人仓库：[CyBerKitTen0009/hemuHomeLab](https://github.com/CyBerKitTen0009/hemuHomeLab)。新检出环境仍默认关闭真实 SSH；凭据和本机设备数据库不会随仓库分发。

## 本地运行

需要 Python 3.12+、uv 和 Node.js 22.17+，推荐 Node.js 24 LTS。

```sh
cd /Users/apple/HomelabControlCenter
python3 scripts/bootstrap.py
uv sync
cd frontend
npm ci
cd ..
sh scripts/dev.sh
```

访问 [本地开发控制台](http://localhost:5173)。用户名为 `admin`；在你自己的终端查看随机生成的初始密码：

```sh
python3 scripts/bootstrap.py --show-password
```

也可以构建前端后仅启动一个服务：

```sh
cd frontend
npm run build
cd ..
.venv/bin/python -m uvicorn backend.hcc.main:app --host 127.0.0.1 --port 8000
```

访问 [本地构建版本](http://localhost:8000)。本地 HTTP 仅绑定回环地址；生产配置强制使用 HTTPS Secure Cookie。

## 已实现

- 带随机初始密码、scrypt 校验、8 小时 HttpOnly / SameSite 会话、登录限流的管理员认证。
- 设备新增、编辑、删除；域名、端口、用户名、服务端凭据引用、单层 SSH 跳板。
- Linux CPU、内存、磁盘、网络吞吐、负载和运行时间；7 天历史，页面最近 120 次采样趋势。
- Docker 容器状态与资源、镜像、Compose 项目、最近日志。
- systemd 服务状态、失败信息和 journal 运行历史。
- 指定 Git 仓库的分支、工作区和最近提交；禁用可选索引写入与 fsmonitor 钩子。
- 统一日志来源、搜索和级别筛选；只读取被采集发现的容器与服务，最多 1000 行。
- 从所选远程设备发起的 HTTP(S) 健康检查，超时、TLS 校验、不跟随重定向。
- 配置导出 / 恢复、审计记录；深浅色主题和响应式布局。
- Docker Compose + Caddy 自定义 HTTPS 端口部署配置。

演示数据始终带 `DEMO / 模拟` 标识。Windows 是模拟离线展示，第一阶段真实采集仅支持 Linux / Linux NAS。第一阶段没有容器启停、服务重启、交互 Shell 或任意命令 API。

## 接入真实 SSH

参阅 [SSH 接入说明](docs/ssh-onboarding.md)。请先提供端口、用户名、专用私钥的本地路径、可信的 SSH 主机指纹；不要把私钥正文粘贴到聊天里。

通用表单默认入口为 `hemu-server.top`；本次用户指定并已验证的实际入口为 `ssh.hemu-server.top:22222`，用户 `hemu`。不会固定解析后的公网 IP。每轮采集建立新连接，以重新解析域名并恢复断线。服务端仅加载你明确指定的凭据文件，不自动读取 `~/.ssh/config`、默认私钥或 SSH Agent。私钥不经过浏览器。

远端需要已有 Python 3。Docker / systemd 不可用或权限不足时，会降级显示错误；程序不会执行 sudo、安装软件或自动调整用户权限。

## 测试

```sh
.venv/bin/python -m pytest -q
cd frontend
npm run check
npm run build
cd ..
HCC_PUBLIC_ORIGIN=https://console.example.com:8443 docker compose config --quiet
```

SSH 集成测试只在回环地址创建临时测试服务器和临时密钥，验证认证、分块输出和拒绝错误主机密钥，不使用家庭设备。需要允许测试进程监听本机端口。

## 部署与备份

参阅 [部署说明](docs/deployment.md)、[架构与安全边界](docs/architecture.md) 及 [验证记录](docs/validation.md)。依赖锁文件为 `uv.lock` 与 `frontend/package-lock.json`。

浏览器导出的 JSON 仅包含设备配置，不包含 SSH 密钥、管理员密码或会话。SQLite 完整备份包括采样与审计，输出文件会清除会话：

```sh
python3 scripts/backup.py backup /absolute/path/homelab-backup.sqlite3
# 恢复之前停止 API；该操作替换本地数据库。
python3 scripts/backup.py restore /absolute/path/homelab-backup.sqlite3 --confirm-server-stopped
```

SSH 凭据与管理员密码应独立保管。日志会对常见凭据格式做脱敏，但不能保证识别所有自定义秘密格式；请只向可信管理员开放控制台。
