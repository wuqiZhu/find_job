@echo off
chcp 65001 >nul
echo ========================================
echo   自动化求职助手 - 本地启动
echo ========================================
echo.

echo [1/3] 检查 Docker Desktop...
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker 未运行！请先启动 Docker Desktop
    echo 下载地址: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)
echo ✅ Docker 已就绪

echo.
echo [2/3] 启动 n8n + PostgreSQL...
docker compose up -d
if %errorlevel% neq 0 (
    echo [错误] 启动失败！
    pause
    exit /b 1
)
echo ✅ 服务启动成功

echo.
echo [3/3] 等待服务就绪...
timeout /t 10 /nobreak >nul

echo.
echo ========================================
echo   ✅ 启动完成！
echo ========================================
echo.
echo   n8n 地址: http://localhost:5678
echo   数据库:   localhost:5433
echo.
echo   首次访问 n8n 需要创建管理员账号
echo.
echo   按任意键打开浏览器...
pause >nul
start http://localhost:5678
