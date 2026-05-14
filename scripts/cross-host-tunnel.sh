#!/usr/bin/env bash
# Maintain a local AO coordinator tunnel from Mac/Linux worker hosts to Ubuntu.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: cross-host-tunnel.sh <ubuntu-ssh-host> [local-port] [remote-port]

Environment:
  FACTORY_V3_SSH_USER          Optional SSH user. Also accepted in host arg.
  FACTORY_V3_SSH_KEY           Optional private key path.
  FACTORY_V3_TUNNEL_LOCAL_PORT Local bind port. Default: 50051.
  FACTORY_V3_TUNNEL_REMOTE_PORT Remote coordinator port. Default: 50051.
  FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT
                                 Optional Ubuntu-side port for reverse worker RuntimeService.
  FACTORY_V3_WORKER_RUNTIME_LOCAL_PORT
                                 Worker-side RuntimeService port. Default: same as reverse port.

Example:
  FACTORY_V3_SSH_USER=ubuntu scripts/cross-host-tunnel.sh ubuntu.example.com
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

ssh_host="$1"
local_port="${2:-${FACTORY_V3_TUNNEL_LOCAL_PORT:-50051}}"
remote_port="${3:-${FACTORY_V3_TUNNEL_REMOTE_PORT:-50051}}"
worker_runtime_remote_port="${FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT:-}"
worker_runtime_local_port="${FACTORY_V3_WORKER_RUNTIME_LOCAL_PORT:-${worker_runtime_remote_port}}"

if [[ -n "${FACTORY_V3_SSH_USER:-}" && "$ssh_host" != *@* ]]; then
  ssh_host="${FACTORY_V3_SSH_USER}@${ssh_host}"
fi

ssh_args=(
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
  -o ExitOnForwardFailure=yes
  -L "${local_port}:127.0.0.1:${remote_port}"
  -N
)

if [[ -n "$worker_runtime_remote_port" ]]; then
  ssh_args+=(
    -R "${worker_runtime_remote_port}:127.0.0.1:${worker_runtime_local_port}"
  )
fi

if [[ -n "${FACTORY_V3_SSH_KEY:-}" ]]; then
  ssh_args=(-i "$FACTORY_V3_SSH_KEY" "${ssh_args[@]}")
fi

if command -v autossh >/dev/null 2>&1; then
  export AUTOSSH_GATETIME="${AUTOSSH_GATETIME:-0}"
  exec autossh -M 0 "${ssh_args[@]}" "$ssh_host"
fi

echo "cross-host-tunnel: autossh not found; falling back to ssh" >&2
exec ssh "${ssh_args[@]}" "$ssh_host"
