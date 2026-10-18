#!/bin/bash
# API Scheduler — 每日定时窗口：拉起 API 栈 → 健康检查 → 运行 N 小时 → 收栈。
# 用途：经费受限时避免 Docker 全天运行耗费真实 API 费用（用户 2026-10-18 提出）。
#
# 用法（手动测试）：
#   ./scripts/api_scheduler.sh 4          # 立即拉起，运行 4 小时后收栈
#
# 用法（每日定时，macOS 建议 LaunchAgent/crontab 调本脚本）：
#   crontab 示例（每天 08:00 起跑 4 小时）：
#     0 8 * * * "/Users/shenqing/Desktop/Deepseek Harness/humanpulse/scripts/api_scheduler.sh" 4 >> /tmp/api_scheduler.log 2>&1
#
# 依赖：docker compose 插件可用（不要覆盖 DOCKER_CONFIG——交接文档 §5 的坑）。
# 诚实性：本脚本只控制容器启停，不碰数据；断档的时段会被 Coverage Calendar 如实画出来，
#         不是故障也不是丢数据，是「这个窗口没开机」。

set -euo pipefail

DURATION_HOURS=${1:-4}
PROJECT_DIR="/Users/shenqing/Desktop/Deepseek Harness/humanpulse"

start_services() {
    echo "[$(date)] Starting services..."
    cd "$PROJECT_DIR"
    docker compose up -d db worker api
    echo "[$(date)] Services started."
}

stop_services() {
    echo "[$(date)] Stopping services..."
    cd "$PROJECT_DIR"
    docker compose down
    echo "[$(date)] Services stopped."
}

check_health() {
    local max_attempts=30
    local attempt=1
    while [ "$attempt" -le "$max_attempts" ]; do
        if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
            echo "[$(date)] API is healthy."
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    echo "[$(date)] Health check failed after $max_attempts attempts."
    return 1
}

main() {
    echo "=== API Scheduler Started ==="
    echo "[$(date)] Window duration: ${DURATION_HOURS}h"

    start_services

    if ! check_health; then
        echo "[$(date)] ERROR: services failed to become healthy; tearing down."
        stop_services
        exit 1
    fi

    echo "[$(date)] Healthy. Running for ${DURATION_HOURS}h..."
    sleep "${DURATION_HOURS}h"

    stop_services
    echo "=== API Scheduler Completed at $(date) ==="
}

trap 'echo "[$(date)] Signal received; stopping services..."; stop_services; exit 0' SIGTERM SIGINT

main "$@"
