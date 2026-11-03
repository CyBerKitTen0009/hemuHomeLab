#!/bin/sh
# Fallback for compose.ssh.yaml only. The current deployment uses direct HTTPS;
# follow docs/deployment.md before switching the server back to SSH-only mode.
set -eu

PROJECT_ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
HCC_SSH_KEY=${HCC_SSH_KEY:-$PROJECT_ROOT/sshkey/id_ed25519}
HCC_KNOWN_HOSTS=${HCC_KNOWN_HOSTS:-$PROJECT_ROOT/config/known_hosts}
HCC_SSH_HOST=${HCC_SSH_HOST:-ssh.hemu-server.top}
HCC_SSH_PORT=${HCC_SSH_PORT:-22222}
HCC_SSH_USER=${HCC_SSH_USER:-hemu}

if [ ! -f "$HCC_SSH_KEY" ] || [ ! -f "$HCC_KNOWN_HOSTS" ]; then
  echo '缺少专用 SSH 密钥或已核验的 known_hosts，请先配置本机接入文件。' >&2
  exit 1
fi

echo 'SSH-only 回退模式：http://localhost:18000（当前 HTTPS 部署请使用 https://ssh.hemu-server.top:20443）'
echo '保持此终端运行；Ctrl+C 断开查看连接，ThinkBook 上的采集服务仍会继续运行。'
exec ssh -nNT -F /dev/null \
  -i "$HCC_SSH_KEY" \
  -o IdentityAgent=none \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$HCC_KNOWN_HOSTS" \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18000:127.0.0.1:18000 \
  -p "$HCC_SSH_PORT" "$HCC_SSH_USER@$HCC_SSH_HOST"
