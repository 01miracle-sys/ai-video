@echo off
chcp 65001 >nul
title AI Video Learning Assistant - 笔记生成

echo ========================================
echo   AI Video Learning Assistant
echo   笔记生成 (Ollama qwen2.5:3b)
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python
    pause
    exit /b 1
)

:: 检查依赖
python -c "import requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安装依赖 requests...
    pip install requests
)

:: 获取输入文件
if exist "%~1" (
    set "INPUT_FILE=%~1"
) else if exist "D:\faster_whisper\outputs\*.txt" (
    echo 找到以下 TXT 文件：
    echo.
    dir /b D:\faster_whisper\outputs\*.txt 2>nul
    echo.
    set /p FILENAME="请输入文件名（不含路径）: "
    set "INPUT_FILE=D:\faster_whisper\outputs\%FILENAME%"
) else (
    set /p INPUT_FILE="请输入 TXT 文件路径: "
)

echo.
echo 开始生成笔记...
echo.

python main.py "%INPUT_FILE%"

echo.
pause
