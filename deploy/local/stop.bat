@echo off
chcp 65001 >nul
echo 正在停止服务...
docker compose down
echo ✅ 服务已停止
pause
