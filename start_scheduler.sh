#!/usr/bin/env bash
set -euo pipefail

# 独立调度进程只部署单实例
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
export APP_ENV=production
exec "$ROOT/.venv/bin/python" scheduler.py
