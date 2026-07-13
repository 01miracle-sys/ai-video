@echo off
chcp 65001 > nul

echo ============================================
echo  AI Video Subtitle Service — 启动中...
echo ============================================
echo.

:: 检查 Python
where python > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

:: 检查依赖
python -c "import fastapi" 2>nul
if %ERRORLEVEL% neq 0 (
    echo ⏳ 正在安装服务端依赖...
    pip install -r requirements-server.txt
    echo.
)

:: 启动服务
echo ✅ 启动服务...
echo.
python server.py

pause
