#!/usr/bin/env bash

set -e

# 执行 alembic 命令
echo "Running database migrations..."
alembic upgrade head

# 启动 web 应用
echo "Starting web..."
python main.py &

# 等待进程完成
wait -n

# 获取退出状态
exit $?
