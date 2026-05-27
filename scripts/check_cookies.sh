#!/bin/bash
# Cookie 健康检查定时任务脚本
# 在服务器上添加 crontab:
# 0 9 * * * /root/projects/find_job/scripts/check_cookies.sh >> /var/log/cookie_check.log 2>&1

cd "$(dirname "$0")/.."

echo "=== Cookie 健康检查 $(date) ==="

python -m job_scraper.cookie_checker --notify --json

echo "=== 完成 ==="
