# 真实 SSH 接入

## 已验证的设备

2026-11-03 已完成 ThinkBook 的首次真实只读连接验证。实际入口为用户指定的 `ssh.hemu-server.top:22222`，用户 `hemu`，使用 `sshkey/` 中的专用 Ed25519 密钥。

本机 `known_hosts` 已有该精确主机和端口的信任条目，只复制匹配条目到被 Git 排除的 `config/known_hosts`，没有进行首次自动信任或修改个人 SSH 配置。`id_ed25519.pub` 是客户端认证公钥，与服务器主机公钥的用途不同。

本机已配置 `config/credentials.json`（0600），并在 `.env` 中启用真实 SSH、停用初始模拟设备；这些文件和运行数据库不进入仓库。新检出环境仍需按下列步骤独立配置。

同日已通过家庭内网添加飞牛 NAS：`192.168.5.100:22`，用户 `hemu`，主机名 `hemu-nas`，使用独立的服务端密码凭据，未配置跳板。只复制本机 `known_hosts` 中该地址已有的精确信任条目，并严格校验；其主机密钥与 ThinkBook 不同，保留为独立设备。密码只保存在本机 `config/credentials.json`（0600），不进入仓库或设备 API。

NAS 已有 Python 3，系统指标、磁盘和 236 个 systemd 服务可读；Docker 守护进程运行，但该用户无权访问 Docker socket，也无权读取系统 journal。未执行 sudo、修改组成员或放宽 socket 权限。后端需位于家庭内网或有到该网段的路由才能直接采集。

## 新环境准备

需要确认的信息：

1. SSH 端口和用户名，以你当前可用连接为准。
2. 认证方式；优先提供一个专用于本控制台的私钥**本地文件路径**，不要在聊天中发送私钥正文。加密私钥的口令仅放在服务端私密配置里。
3. 已通过可信渠道核验的 SSH 主机 SHA256 指纹，以及仅包含所需主机的 OpenSSH `known_hosts` 文件路径。
4. 设备上已有 Python 3，以及当前用户是否可读取 Docker、systemd journal。权限不够时先展示受限状态，不自动提权。
5. 可选：需要查看的 Git 仓库绝对路径，以及健康检查名称和 URL。

不要将未经核验的 `ssh-keyscan` 输出直接当作信任依据。可以通过你已有的可信会话或主机控制台核验：

```sh
# 在你已信任的远程终端执行，只读取主机公钥指纹。
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

非标准端口的 known_hosts 行通常为：

```text
[hemu-server.top]:ACTUAL_PORT ssh-ed25519 TRUSTED_HOST_PUBLIC_KEY
```

准备服务端配置（路径需改成真实值）：

```json
{
  "thinkbook": {
    "username": "ACTUAL_USER",
    "private_key": "/absolute/path/to/dedicated/key",
    "known_hosts": "/absolute/path/to/dedicated/known_hosts"
  }
}
```

将其保存在 `config/credentials.json`，文件和私钥权限设为 `0600`。此文件在 `.gitignore` 和 Docker 构建上下文排除规则中。不要将整个个人 `.ssh` 目录挂载到容器。

如果现有环境仅使用密码认证，可在服务端配置中用 `password` 代替 `private_key`。密码只在该 0600 文件中管理，不通过设备 API 传递，不在浏览器输入。加密私钥可额外使用服务端 `passphrase` 字段。程序优先公钥认证，不尝试默认私钥或交互式认证。

用户确认提供凭据后，再将 `.env` 中 `HCC_ENABLE_SSH` 改为 `true` 并重启本地 API。浏览器添加一个真实 SSH 设备：本次主机为 `ssh.hemu-server.top`、端口 `22222`、用户名 `hemu`、认证配置名 `thinkbook`。不要直接把演示数据理解为真实设备。

首次验证只读取系统、容器、服务等信息。请求中的 Git 路径和健康 URL 通过 JSON + Base64 传递到固定采集脚本，日志目标必须来自最近已发现的资源；没有自由输入命令的 API。

NAS 接入时，若只有 ThinkBook 暴露公网入口，则先为 NAS 配置独立服务端凭据和主机指纹，再选择 ThinkBook 为跳板；NAS 主机填其家庭内网地址。跳板及目标分别严格验证主机密钥，不开放额外公网端口。
