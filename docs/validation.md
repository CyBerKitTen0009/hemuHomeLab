# 验证记录

本轮验证日期：2026-11-03。ThinkBook 与飞牛 NAS 均已完成真实 SSH 只读接入；NAS 部分资源受账户权限限制。

自动化覆盖包括：认证与会话过期、CSRF、Origin / Host 防护、请求体限制、登录限流、设备 CRUD、模拟指标与历史、日志目标白名单、搜索、配置恢复原子校验、跳板约束、审计、常见凭据脱敏、删除演示设备后的持久行为。

SSH 集成测试仅使用本机回环地址临时 SSH 服务：专用 Ed25519 密钥认证、分块 stdout 拼接、固定采集脚本构建、journal 权限不足的错误分类、错误主机密钥拒绝。错误主机密钥时未下发采集命令。

## 最终结果

- 后端：`pytest -q`，**24 passed**。有 1 条 Starlette 关于测试客户端 `httpx` 的上游弃用提示，不影响当前测试结果。
- 前端：`npm run check`，**0 errors / 0 warnings**；`npm run build` 成功。
- Compose：使用占位 HTTPS Origin 执行 `docker compose config --quiet` 通过；占位域名没有进行连接或部署。
- 备份：在线备份演示数据库，再恢复到临时数据库；完整性检查为 `ok`，3 台原始模拟设备保留，登录会话数为 0。
- 浏览器：实际构建版本由 FastAPI 提供，验证登录、设备总览与资源趋势、Docker 镜像 / Compose、异常 systemd 服务直达 journal、日志 ERROR 过滤、Git 状态、设备新增与编辑、审计记录、明暗主题。
- 响应式：桌面 1440 × 1000，手机 390 × 844；手机导航可展开，页面宽度未超出视口，窄屏标题维持单行；浏览器控制台无 error / warn 记录。
- 浏览器测试新建的模拟设备已清理；首轮保留原始三台模拟设备，真实 ThinkBook 验证成功后，本机已移除这三条初始模拟配置并关闭自动演示初始化。
- 截图位于 `artifacts/overview-desktop.jpg` 与 `artifacts/overview-mobile.jpg`。

## 依赖审计

`npm audit` 报告 4 条 low 告警，均来自同一条构建工具依赖链：`adapter-static → kit → vite-plugin-svelte → deepmerge`。当前安装 `deepmerge 4.3.1`，上游 [GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4) 说明暂无修复版本。没有为了清除告警强制降级至过时的框架版本。

这是 Node 构建环境的依赖；最终部署镜像只包含静态前端构建产物和 Python API，运行时不包含 Node 或该构建依赖。构建配置不合并浏览器提交的不可信对象。后续更新锁文件时应重新检查上游修复状态。

## ThinkBook 真实接入

- 实际地址：`ssh.hemu-server.top:22222`，用户 `hemu`，Ed25519 密钥认证。
- 信任来源：本机已有精确主机与端口的 `known_hosts` 条目，严格校验成功，没有自动接受扫描得到的新密钥。
- 系统：主机名 `omarchy`，OS `Omarchy`；已有 Python 3，采集脚本直接内联执行，未安装依赖或写入远程脚本文件。
- 首次真实指标：CPU 25.9%，内存 35.2%，磁盘 21.3%；实际采样会继续变化。
- Docker：可读取，发现 2 个容器；systemd：可读取，发现 158 个服务。
- ThinkBook 首次接入时，本机 Web API 切换为唯一真实设备，`demo=false`；后续 NAS 作为第二台真实设备添加，实际指标与历史通过已认证 API 提供。
- 实际 Docker 容器日志和 SSH 服务 journal 各读取最近 10 行，均通过已认证 Web API 返回真实数据；未输出日志正文至仓库，journal 未提示权限不足。
- 未发现的容器目标返回 422，任意命令 API 返回 404；会话仍为只读模式。
- SSH 私钥、公钥、专用主机记录、管理员密码、服务端凭据与数据库均由 Git 排除，并在推送前检查暂存区。

## NAS 家庭内网接入

- 实际地址：`192.168.5.100:22`，用户 `hemu`，密码认证；独立服务端凭据，直接连接，无跳板。
- 信任来源：本机已有该精确地址的 `known_hosts` 条目；校验成功，主机密钥与 ThinkBook 不同，没有覆盖 ThinkBook 配置。
- 系统：主机名 `hemu-nas`，Debian GNU/Linux 12，内核 `6.18.18.c952-trim`，发现飞牛 `trim_*` 服务；已有 Python 3，未安装软件或写入远程采集文件。
- 已认证 API 验证真实指标、4 个挂载点、236 个 systemd 服务与连续历史采样；两台设备均为在线且 `demo=false`。
- 浏览器已核验两台设备总览、NAS 资源趋势与日志权限提示；本机截图为 `artifacts/nas-live-overview.png`。
- Docker 守护进程为 active，但当前用户不能访问 `/var/run/docker.sock`；journal 明确返回权限不足，API 返回 `remote_permission_denied`，页面展示读取权限提示。
- 密码、专用主机记录与设备数据库仅保存在被 Git / Docker 构建上下文排除的本地文件中，凭据文件权限为 0600；设备 API 不返回密码。
- 未执行 sudo、调整组成员或放宽 socket 权限。NAS 的内网直连要求后端可访问家庭网段。

当前限制：Mac 的 Docker 引擎未运行，尚未验证镜像实际构建与容器 HTTPS 启动；NAS 的 Docker / journal 读取权限、实际 Git 仓库路径和健康检查 URL 尚未配置。没有向 ThinkBook / NAS 安装控制台或修改网络、服务配置。
