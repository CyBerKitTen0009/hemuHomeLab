# 架构与安全边界

```text
浏览器（SvelteKit SPA）
    │ 同源 HTTP（仅本地）/ HTTPS 自定义端口（生产）
    ▼
Caddy（生产）→ FastAPI（认证、CSRF、Origin/Host、审计、固定 API）
                    ├── SQLite：设备、快照、历史、会话哈希、审计
                    ├── 服务端私密文件：管理员密码、专用 SSH 凭据
                    └── AsyncSSH → hemu-server.top → ThinkBook
                                      └── 可选单层跳板 → NAS
```

## 数据模型

- `devices`：JSON 配置（名称、DNS 主机、端口、用户名、模式、凭据引用、跳板、Git 路径、健康检查）。私钥不进入数据库。
- `snapshots`：最近一次连接结果或最近成功数据加连接错误；每台设备一条。
- `samples`：只写入成功采集的资源指标，保留 7 天；页面最近 120 个样本。错误采样不画成 0。
- `sessions`：随机 48 字节会话令牌的 SHA256 哈希、独立 CSRF token、8 小时有效期。
- `audit`：登录、设备配置变更、刷新、日志读取、导出恢复，最多保留 10000 条，页面显示最近 100 条。
- `metadata`：一次性演示数据初始化标记，删除演示设备后不会重生。

## 连接生命周期

每台设备使用锁，最多 3 台并发采集。启动和轮询时采集，手动刷新需认证及 CSRF。连接 / 认证超时 10 秒，采集总超时 50 秒，单次 SSH 输出上限 1 MiB。重试由下一轮采集触发，重新解析域名，不缓存动态公网 IP。

SSH 禁用用户默认配置和 Agent，只加载命名凭据配置。私钥权限必须为 0600 或更严格。跳板及目标分别使用显式 `known_hosts` 校验；未知、不匹配或撤销的密钥不得放行。程序不执行自动信任或密钥扫描。

远程采集通过已有 Python 3 运行内联脚本，读取 `/proc`，调用固定的 Docker / systemctl / git 命令和 HTTP GET。没有远程安装、sudo、文件写入、服务重启等命令。Git 禁用索引可选写入、fsmonitor、钩子；HTTP 探测不使用继承代理、不跟随重定向、校验 TLS。

日志只按已发现的资源读取。服务名和容器名有格式校验和安全引用；浏览器不能提供命令片段。日志、设备健康返回仍是敏感运维信息，需要可信管理员。

## Web 防护

随机管理员密码存储在只读服务端秘密文件，使用 scrypt 校验。生产 HTTPS、Secure + HttpOnly + SameSite=Strict Cookie，写入 API 需要独立 CSRF token。Origin 与 Host 显式允许列表、跨站请求拒绝、128 KiB 请求体限制、登录限流（每来源 8 次 / 5 分钟，全局 100 次 / 5 分钟）。反向代理来源 IP 不盲信，因此默认代理环境的限流按代理对端聚合。

所有 API 数据响应 `no-store`，CSP 禁止第三方脚本和框架嵌入。未实现 CORS 和任意命令执行 API。初始本地 HTTP 只面向回环地址，生产强制 HTTPS。

## 依据与限制

前端使用当前 [SvelteKit 适配器配置](https://svelte.dev/docs/kit/adapters)；后端生命周期遵循 [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)；SSH 采用 [AsyncSSH 的显式 known_hosts 与 tunnel 配置](https://asyncssh.readthedocs.io/en/latest/api.html)。

第一阶段不支持 Windows 实际采集，不采集任意目录，不跟踪持续日志流，不提供远程变更。健康检查以配置 URL 的 HTTP 状态为依据（2xx / 3xx 为正常），不等同于业务功能验证。脱敏仅覆盖常见秘密格式；主机本身的可信度、账户权限、凭据与 TLS 证书运维仍由管理员负责。
