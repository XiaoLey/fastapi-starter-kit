#!/usr/bin/env bash
set -euo pipefail

# 使用脚本所在目录，不依赖调用方的工作目录
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

export APP_ENV=production

# 独立调度进程只部署单实例
# 由调度进程直接接收停止信号
exec "$ROOT/.venv/bin/python" scheduler.py
