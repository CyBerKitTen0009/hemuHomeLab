# 随身 Mac 主动上报

Mac 通过现有自定义端口 HTTPS 向 ThinkBook 发送只读数据，适用于经常离开家庭网络的笔记本。采集端不监听端口，不需要给 Mac 配公网 IP、入站 SSH 或路由器映射。

## 范围与状态

- 系统：CPU、内存、APFS 数据卷空间、物理网卡收发、负载、运行时间。
- Git：本机明确允许的仓库路径、分支、工作区变更数量、最近提交。不上传源码、变更内容、个人日志、进程命令行或 GitHub 登录凭据；不执行 fetch、pull、commit。
- 当前间隔 30 秒；120 秒未收到上报时显示离线，保留最后一次指标与历史。睡眠、关机、断网时不会补造采样；唤醒、网络恢复后重试。
- 网络错误按 5、10、20、40、60 秒退避，上限 60 秒。每次连接重新解析域名，严格验证项目证书与主机名，不跟随重定向。
- 公共 Wi-Fi 的登录页、网络对 20443 的封锁仍可能阻止上报；采集端会保留重试，不代替用户登录网络或改变代理、防火墙配置。
- 当前不采集 Mac Docker、launchd 服务或个人日志。Windows 采集不在此接入方式的已实现范围内。

GitHub 仓库列表用于发现候选，不代表这些仓库已在设备上部署。只接入已匹配到的本地仓库；没有自动克隆其他仓库。控制台最多配置 20 个 Git 路径，可搜索项目名称、路径和分支。

## 凭据与本机范围

每台设备有独立上报令牌，只能获取自己的仓库配置、提交自己的指标；不能访问管理员 API、其他设备或执行命令。服务端仅保存令牌哈希，配置导出和审计不会包含令牌。

Mac 将令牌保存在 `config/mac-agent.json`，权限 0600，已被 Git 和 Docker 构建排除。采集端还要求本机 `allowed_git_paths` 明确允许每个路径，并检查解析后的真实路径；网页添加其他路径时，先显示本机未允许的提示，不读取该仓库。

HTTPS 使用已有部署的公开证书文件，私钥仅留在 ThinkBook。核验方式和证书指纹见 [部署说明](deployment.md)。证书更新后需同步 Mac 的公开证书文件，采集端下轮连接重新加载；没有安装全局信任根。

## 安装与新增仓库

在本项目目录准备独立运行环境（只安装采集依赖）：

```sh
uv venv --python 3.12 data/mac-agent-venv
uv pip install --python data/mac-agent-venv/bin/python 'psutil==7.2.2'
```

将已经核验的项目公开证书放在 `data/thinkbook-selfsigned.pem`，使用管理员密码文件注册设备；密码不会写入采集服务配置。新环境需要用 `--password-file` 指向当前控制台的管理员密码文件。

```sh
python3 scripts/enroll-mac-agent.py \
  --server https://ssh.hemu-server.top:20443 \
  --certificate data/thinkbook-selfsigned.pem \
  --repo /Users/YOU/Projects/example
data/mac-agent-venv/bin/python -m backend.hcc.mac_agent --config config/mac-agent.json --once
python3 scripts/install-mac-agent.py
```

`enroll-mac-agent.py --repo ...` 可重复执行，将新增路径加入本机允许列表和该设备的监控配置，同时轮换上报令牌；现有路径和历史保留。运行中的采集服务会重新加载配置，无需再次安装。若不希望监控某个已允许仓库，可直接在控制台编辑设备，移除该 Git 路径。

安装器只创建本用户 `~/Library/LaunchAgents/top.hemu.homelab.mac-agent.plist`，用户登录时启动，无需 sudo。采集环境位于 `data/mac-agent-venv`，与开发环境独立。移动项目目录前需重新配置安装路径。

## 维护

```sh
launchctl print "gui/$(id -u)/top.hemu.homelab.mac-agent"
tail -n 20 data/mac-agent.log
```

日志只记录连接状态变化，不记录令牌、上报正文或 Git 提交信息，单文件 1 MiB，保留 2 个轮转文件。

停止常驻服务：

```sh
launchctl bootout "gui/$(id -u)/top.hemu.homelab.mac-agent"
```

删除该用户 LaunchAgents 目录下的对应 plist 可取消下次登录启动。控制台删除设备、切换采集模式或恢复设备配置备份会撤销上报令牌；恢复后需重新注册。注册工具不会自动替代已删除的设备，需要先备份并移走旧本机采集配置，再建立新的设备记录。
