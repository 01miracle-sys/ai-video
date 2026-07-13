"""
AI-Video Web 服务入口
============================================

将桌面端的视频语音识别 + 翻译能力暴露为 REST API，
供手机浏览器（Tampermonkey 脚本）或独立 Web 页面调用。

用法:
    python server.py
    # 然后浏览器访问: http://localhost:8000

依赖安装:
    pip install fastapi uvicorn yt-dlp
"""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""
    app = FastAPI(
        title="AI Video Subtitle Service",
        description="Provide video ASR + translation subtitle service for mobile browsers",
        version="1.0.0",
    )

    # ─── CORS（允许手机浏览器跨域访问） ─────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发阶段允许所有来源
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    # ─── 加载配置 ─────────────────────────────────
    config_path = Path("config/settings.yaml")
    config: dict = {}
    if config_path.exists():
        import yaml
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    server_cfg = config.get("server", {})
    max_concurrent = server_cfg.get("max_concurrent_tasks", 2)
    cleanup_hours = server_cfg.get("cleanup_hours", 24)

    # ─── 初始化任务管理器 ──────────────────────────
    from src.server.api import init_task_manager
    init_task_manager(
        max_concurrent=max_concurrent,
        cleanup_hours=cleanup_hours,
    )

    # ─── 注册 API 路由 ────────────────────────────
    from src.server.api import router as api_router
    app.include_router(api_router)

    # ─── 挂载静态文件（Web 界面） ───────────────────
    web_dir = Path("web")
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


def main() -> None:
    """启动服务"""
    # 加载配置
    config_path = Path("config/settings.yaml")
    config: dict = {}
    if config_path.exists():
        import yaml
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 8000)

    app = create_app()

    # 获取局域网 IP
    local_ip = _get_local_ip()

    # 设置 stdout 编码为 UTF-8，避免 Windows GBK 控制台打印 emoji 报错
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

    print("=" * 60)
    print("  AI Video Subtitle Service")
    print("=" * 60)
    print(f"  Local:     http://localhost:{port}")
    if local_ip:
        print(f"  Network:   http://{local_ip}:{port}")
    print(f"  API docs:  http://localhost:{port}/docs")
    print(f"  Health:    http://localhost:{port}/api/health")
    print("=" * 60)
    print("  Install the Tampermonkey userscript on your phone")
    print("  or open the network URL above in your mobile browser")
    print("=" * 60)
    print()

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


def _get_local_ip() -> str:
    """获取本机局域网 IP 地址"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


if __name__ == "__main__":
    main()
