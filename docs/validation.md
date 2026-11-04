# 验证记录

初次验证日期：2026-11-03；2026-11-04 的项目监控与 Mac 主动上报接入记录见文末。ThinkBook 与飞牛 NAS 均已完成真实 SSH 只读接入，Mac 已通过公网主动上报；NAS 部分资源受账户权限限制，目前按用户说明关机。

自动化覆盖包括：认证与会话过期、CSRF、Origin / Host 防护、请求体限制、登录限流、设备 CRUD、模拟指标与历史、日志目标白名单、搜索、配置恢复原子校验、跳板约束、审计、常见凭据脱敏、删除演示设备后的持久行为。

SSH 集成测试仅使用本机回环地址临时 SSH 服务：专用 Ed25519 密钥认证、分块 stdout 拼接、固定采集脚本构建、journal 权限不足的错误分类、错误主机密钥拒绝。错误主机密钥时未下发采集命令。

## 最终结果

- 后端：2026-11-04 运行 `python -m pytest -q`，**39 passed**；随后补充断网恢复与凭据重新加载回归，`backend/tests/test_mac_agent.py` 定向运行 **4 passed**。有 1 条 Starlette 关于测试客户端 `httpx` 的上游弃用提示，不影响当前测试结果。
- 前端：`npm run check`，**0 errors / 0 warnings**；`npm run build` 成功。最终部署镜像 `hemu-hcc:99944fc` 在 ThinkBook 上再次完成类型检查与构建，应用健康。
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

## ThinkBook 常驻部署

- 已在 ThinkBook 上使用现有 Docker Engine / Compose 构建镜像 `hemu-hcc:a66342c`；镜像内前端类型检查、构建与 Python 锁文件依赖安装成功。
- 实际容器 `hemu-homelab-app-1` 健康运行，仅发布 `127.0.0.1:18000`；运行用户 UID 10001，只读根文件系统、丢弃 capabilities、禁止提权，凭据只读挂载。
- 修复 Compose 的 tmpfs 流式列表逗号解析问题，避免 `mode=1777` 被误当作第二个挂载路径；SSH 和 HTTPS 两份配置均已修正。
- 通过严格主机密钥校验的既有 SSH 转发验证真实登录、会话、两台设备在线状态、历史和 NAS journal 权限提示；管理员密码沿用，设备 API 不返回 NAS 密码。
- 浏览器验证部署实例登录与两台真实设备总览，截图为 `artifacts/thinkbook-deployed-overview.png`。
- 迁移保留两台设备 ID 与历史，清除迁移会话。ThinkBook 自身改走 `host.docker.internal:22`，NAS 仍为内网直连；已验证自连接主机密钥与此前 ThinkBook 一致。
- Docker 已开机启用，容器设置 `unless-stopped`；实际重启本项目容器后，两台设备重新采集成功，未重启 ThinkBook 或既有业务容器。

## 独立自签名 HTTPS

- 用户确认 19443 属于另一个项目，选择本项目使用 TCP 20443，并自行添加路由器转发；同时选择接受自签名证书提示，不使用阿里云 AccessKey。
- 根域名暂无公网 A / AAAA 记录，改为复用现有 `ssh.hemu-server.top` 解析，入口 `https://ssh.hemu-server.top:20443`；没有修改 DNS 或固定公网 IP。
- 在 ThinkBook 本地生成独立 EC 证书与私钥，证书有效至 2027-11-03；TLS 目录 0700、文件 0600、仅 HTTPS 容器只读挂载，私钥没有传到 Mac 或 Git。
- 使用官方 Caddy 派生镜像，移除二进制低端口 file capability；容器丢弃全部 capabilities 后能正常启动并监听 20443。应用和 HTTPS 容器均只读根文件系统，保持 `unless-stopped`。
- Caddy 配置验证通过；内网与公网域名、实际公网地址的 TLS 1.3 健康请求均返回 200。直接通过公网域名、显式信任项目证书并严格核验域名后，真实 HTML、登录、Secure / HttpOnly / SameSite 会话、两台设备在线数据和历史均通过，Web 请求不依赖 SSH 转发。
- 未认证设备请求 401、跨来源请求 403、未配置的 HTTPS Host 421。测试没有使用 `verify=False`，没有安装系统信任根或自动跳过浏览器证书警告。
- 已有 `digital-life-caddy.service` 仍为 active、MainPID 1082，其公网 19443 的 TLS 1.3 握手通过；本项目没有改动该代理。
- 用户手动执行 `sudo ufw allow 20443/tcp comment 'Homelab HTTPS'`；只读核查确认对应入站 ACCEPT 规则存在。
- 放行后，原 Docker 桥接发布方式仍超时。利用自动退出的临时诊断容器，仅观察物理网卡与 Meta 的 TCP 握手元数据，确认路由器转发的 20443 SYN 已到达 ThinkBook；同端口内网连接正常。没有读取载荷或修改路由、代理、内核防火墙规则。
- 将独立 HTTPS 容器改为 Linux 主机网络，直接监听 20443 并反向代理到应用回环端口 18000，公网握手随即恢复。配置验证和实际容器重建通过；HTTPS 仍丢弃全部 capabilities、根文件系统只读，应用容器与数据保持原状。
- 用户再次用手机关闭 Wi-Fi、通过流量访问，已确认看到登录页。

当前限制：浏览器首次自签名提示需用户手动确认，证书到期需手动更新。NAS 的 Docker / journal 读取权限仍受限。路由器映射与 UFW 规则由用户手动添加，代理未更改 DNS、SSH 服务或既有反向代理配置。

## 2026-11-04 Git 与健康检查接入

- 用户说明 NAS 当前关机，先推进其他内容；保留 NAS 设备与凭据配置，开机后按原轮询自动重试。
- 通过已有 systemd 工作目录和 Docker Compose 标签只读定位 Digital Life 项目，确认 Git 仓库为 `/home/hemu/Projects/digital-life-os`。没有读取无关的个人文件或修改该项目。
- 从项目文档与路由定义确认 `/healthz`，实际 `http://127.0.0.1:8090/healthz` 返回 200；需要认证的其他接口未接入。
- 修复编辑设备无条件清除历史的问题：名称、分类、Git 路径与健康检查修改保留历史，更换 SSH 连接配置或采集模式清除旧目标指标。新增两项 API 回归，验证保留历史及更换连接后清除旧指标；后端共 26 项通过。
- 更新前通过 SQLite 在线 backup API 生成权限 0600 的完整备份，`quick_check` 为 `ok`；仅传输已提交源码构建 `hemu-hcc:b395ef1`，仅重建本项目后端，容器健康检查通过。前端未修改，复用已验证的构建缓存。
- 通过公网 HTTPS 正式 API 导出配置，再向 ThinkBook 添加一个 Git 仓库与两个健康目标：控制台 API、Digital Life。配置更新经过认证、CSRF 与审计。
- 实际 Git 采集为 `main`、工作区干净、最近提交 `2a295a4`；两项健康检查均为 healthy / HTTP 200。Web 请求严格校验项目证书与域名。
- 更新后全部采样核查：ThinkBook 从 1529 条增加至 1536 条、NAS 保持 701 条，两台最早采样时间均不变；数据库完整性为 `ok`。最近历史曲线保留，NAS 配置与接入前一致。

## 2026-11-04 随身 Mac 接入

- 用户确认系统指标、选定 Git 分支 / 提交 / 工作区状态的范围，并确认登录自启动。使用已登录的 GitHub CLI 只读查询 12 个仓库记录，匹配本机 5 个仓库：HomelabControlCenter、IncidentPilot、TraceForge、dsh-quota-dashboard、论文；没有自动克隆其他仓库。
- 已安装独立 Python 运行环境与本用户 LaunchAgent，`RunAtLoad`、`KeepAlive` 已配置，实际状态为 running。第一次正式上报于本地时间 11:30:51 到达，后台持续采样；公网总览已观察到 17 次连续采样与真实资源趋势。
- Mac 仅主动连接现有 HTTPS 域名和端口，严格核验项目公开证书与域名。实际临时 TLS 服务测试验证：显式信任可连接、错误信任根被拒绝、重定向不转发凭据。
- 设备专用令牌不能读取管理员 API 或其他设备；实际生产请求验证本设备配置返回 200，其他设备配置与管理员设备列表均返回 401。服务端只存令牌哈希，Mac 配置权限 0600；删除设备、切换采集模式、恢复配置时撤销令牌的回归均通过。
- 自动化覆盖请求字段边界、非有限指标、超限 / 未配置仓库、重复路径、上报频率限制、本机仓库允许列表与符号链接逃逸拒绝。Git 采集固定为只读命令，不上传源码、变更正文或个人日志。
- 浏览器预览实际观察到停止上报 120 秒后的离线提示、最后采样时间和历史保留；新增定向回归模拟网络中断、5 秒退避、凭据文件轮换、恢复上报与恢复正常间隔，日志不含令牌。未实际执行 Mac 重启、退出登录或切换 Wi-Fi。
- 更新前通过 SQLite 在线 backup API 备份，完整性为 `ok`。部署后 ThinkBook 采样从 1756 条增加至 1770 条、NAS 保持 701 条，原设备最早采样时间均不变；Mac 新增连续历史，数据库完整性仍为 `ok`。最终页面更新前又备份了包含 Mac 注册信息的数据库。
- 最终镜像 `hemu-hcc:4c5da3f` 仅重建本项目应用，HTTPS 容器继续运行；Mac 无需重新注册即可继续上报。Linux 镜像未安装仅供 Mac 使用的 psutil。
- 公网浏览器核验三台真实设备：ThinkBook 与 Mac 在线，NAS 关机显示连接异常并标识“上次数据”；Mac Git 页面展示全部 5 个仓库的分支、提交与变更数量。截图为 `artifacts/mac-live-overview.png`、`artifacts/mac-live-git.png`。临时预览服务与测试页面已关闭，正式服务保持运行。
- Windows 尚未开机，未创建伪装成真实设备的记录。公共 Wi-Fi 登录页或封锁 20443 的网络可能暂时阻断上报，网络恢复后采集服务继续重试。

## 2026-11-04 Apple 风格前端重写

- 按用户要求重写整套样式：系统字体、浅灰背景、白色圆角分组、蓝色交互色、分组侧栏、分段图表控件；浅色为默认，深色主题独立设计。登录页改为居中表单，支持显示 / 隐藏密码；设备、Docker、系统服务、Git、日志、健康检查、设置与弹窗采用统一控件。
- 总览标题与页面说明简化，Mac 总览显示近期项目；离线设备保留“上次数据”与弱化的资源进度条，异常状态不依赖颜色单独表达。手机加入搜索入口、导航遮罩及更大的触控区域；收起导航时不进入可访问树，Escape 可关闭导航和搜索。
- 独立预览数据库验证登录、主题切换、设备切换、Mac 配置弹窗、Git 筛选、手机搜索与导航、Docker 镜像表格、日志读取 / 级别过滤、设置与审计。桌面 1440 × 1000、手机 390 × 844 检查通过；手机页面滚动宽度与可用视口宽度一致，表格在容器内横向滚动。
- 本机与远端 Docker 构建均完成 `npm run check`（0 errors / 0 warnings）及 `npm run build`。无后端或依赖变更，本轮未重复执行后端测试。
- 更新前使用 SQLite 在线 backup API 生成权限 0600 的完整备份。只重建应用至 `hemu-hcc:99944fc`，健康检查通过，HTTPS 容器继续运行。更新后数据库完整性为 `ok`，原设备最早采样时间及全部历史保留，上报令牌记录数未变，Mac 无需重新注册。
- 正式公网浏览器核验新版总览、Mac 近期项目、全部 5 个 Git 仓库及筛选空状态 / 清除筛选；控制台没有 error / warn。ThinkBook 与 Mac 持续在线，NAS 按用户说明关机；实际 HTTPS API 登录和设备读取成功。
- 正式页面截图：`artifacts/apple-ui-live-overview.png`、`artifacts/apple-ui-live-git.png`。预览实例已与正式数据库隔离，不会将模拟数据写入正式部署。
