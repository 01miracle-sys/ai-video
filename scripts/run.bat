@echo off
chcp 65001 >nul
title AI Video Learning Assistant

echo ========================================
echo   AI Video Learning Assistant
echo   %~n0
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python
    pause
    exit /b 1
)

:: 检查参数
if "%~1"=="" (
    echo 用法: run.bat ^<视频文件或 TXT 文件^> [选项]
    echo.
    echo 示例:
    echo   run.bat video.mp4              全流程：转文字 + 笔记
    echo   run.bat video.mp4 --burn       全流程 + 烧录字幕
    echo   run.bat output\test.txt        已有 TXT，仅生成笔记
    echo.
    set /p INPUT="请输入文件路径: "
) else (
    set "INPUT=%~1"
    shift
)

echo 输入: %INPUT%
echo.

python main.py "%INPUT%" %*

echo.
pause
