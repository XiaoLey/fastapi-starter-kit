#!/usr/bin/env bash
set -euo pipefail

# 发布前单独迁移，运行阶段只使用已安装环境
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
export APP_ENV=production
exec "$ROOT/.venv/bin/python" main.py
