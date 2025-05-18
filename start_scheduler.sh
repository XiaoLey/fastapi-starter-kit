#!/usr/bin/env bash

set -e

# 启动事件调度任务
echo "Starting scheduler..."
python scheduler.py &

# 等待进程完成
wait -n

# 获取退出状态
exit $?
