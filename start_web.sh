#!/usr/bin/env bash
set -euo pipefail

# 使用脚本所在目录，不依赖调用方的工作目录
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

export APP_ENV=production

# 发布前单独迁移，运行阶段只使用已安装环境
# 由应用进程直接接收停止信号
exec "$ROOT/.venv/bin/python" main.py
