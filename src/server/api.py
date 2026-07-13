"""
FastAPI API 路由定义
"""

import os
import shutil
import threading
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from src.server.models import (
    ErrorResponse,
    HealthResponse,
    SubtitleRequest,
    TaskProgress,
    TaskStatus,
    TaskSubmitResponse,
)
from src.server.task_manager import TaskManager
from src.translate.translator import (
    create_translator,
    check_translation_available,
    srt_to_vtt,
)

# ─── 全局任务管理器 ──────────────────────────────
task_manager: Optional[TaskManager] = None


def init_task_manager(max_concurrent: int = 2, cleanup_hours: int = 24) -> TaskManager:
    """初始化全局任务管理器（启动时调用）"""
    global task_manager
    task_manager = TaskManager(
        max_concurrent=max_concurrent,
        cleanup_hours=cleanup_hours,
        data_dir="outputs/tasks",
    )
    return task_manager


router = APIRouter(prefix="/api")


# ─── 健康检查 ─────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """服务健康检查"""
    from src.translate.translator import check_translation_available

    return HealthResponse(
        status="ok",
        ollama_connected=check_translation_available("ollama"),
        active_tasks=task_manager.active_count() if task_manager else 0,
    )


# ─── 提交字幕任务（URL 模式）────────────────────────

@router.post(
    "/subtitle",
    response_model=TaskSubmitResponse,
    responses={429: {"model": ErrorResponse, "description": "任务队列已满"}},
)
async def submit_subtitle_task(req: SubtitleRequest):
    """通过视频 URL 提交字幕生成任务"""
    if task_manager is None:
        raise HTTPException(status_code=503, detail="服务尚未初始化")

    if not task_manager.can_accept_task():
        raise HTTPException(
            status_code=429,
            detail=f"任务队列已满（最多 {task_manager.max_concurrent} 个并发），请稍后再试",
        )

    task = task_manager.create_task(
        video_url=req.video_url,
        source_language=req.source_language,
        target_language=req.target_language,
        translation_provider=req.translation_provider or "ollama",
        task_name=req.task_name or "",
    )

    # 启动后台处理线程
    thread = threading.Thread(
        target=_process_subtitle_task,
        args=(task.task_id,),
        daemon=True,
    )
    thread.start()

    return TaskSubmitResponse(
        task_id=task.task_id,
        message=f"任务已提交，正在处理「{task.video_url[:50]}...」",
    )


# ─── 提交字幕任务（文件上传模式）────────────────────

@router.post(
    "/subtitle/upload",
    response_model=TaskSubmitResponse,
    responses={429: {"model": ErrorResponse}},
)
async def upload_subtitle_task(
    file: UploadFile = File(..., description="视频文件"),
    source_language: str = Form(default="ja"),
    target_language: str = Form(default="zh"),
    translation_provider: Optional[str] = Form(default=None),
):
    """上传视频文件提交字幕生成任务"""
    if task_manager is None:
        raise HTTPException(status_code=503, detail="服务尚未初始化")

    if not task_manager.can_accept_task():
        raise HTTPException(
            status_code=429,
            detail=f"任务队列已满（最多 {task_manager.max_concurrent} 个并发），请稍后再试",
        )

    # 保存上传的文件
    upload_dir = Path("outputs/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    try:
        with file_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    task = task_manager.create_task(
        video_file_path=str(file_path),
        source_language=source_language,
        target_language=target_language,
        translation_provider=translation_provider or "ollama",
        task_name=file.filename,
    )

    thread = threading.Thread(
        target=_process_subtitle_task,
        args=(task.task_id,),
        daemon=True,
    )
    thread.start()

    return TaskSubmitResponse(
        task_id=task.task_id,
        message=f"文件「{file.filename}」已上传，开始处理",
    )


# ─── 任务状态 ─────────────────────────────────────

@router.get(
    "/subtitle/{task_id}/status",
    response_model=TaskProgress,
    responses={404: {"model": ErrorResponse}},
)
async def get_task_status(task_id: str):
    """查询任务处理进度"""
    if task_manager is None:
        raise HTTPException(status_code=503, detail="服务尚未初始化")

    progress = task_manager.get_task_progress(task_id)
    if progress is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return progress


# ─── 获取字幕 ─────────────────────────────────────

@router.get(
    "/subtitle/{task_id}/vtt",
    response_class=PlainTextResponse,
    responses={
        200: {"content": {"text/vtt": {}}},
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
async def get_subtitle_vtt(task_id: str):
    """获取 WebVTT 格式字幕"""
    if task_manager is None:
        raise HTTPException(status_code=503, detail="服务尚未初始化")

    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    if task.status == TaskStatus.ERROR:
        raise HTTPException(status_code=400, detail=f"任务处理失败: {task.error_message}")
    if task.status != TaskStatus.DONE:
        raise HTTPException(status_code=400, detail=f"任务尚未完成（当前状态: {task.status.value}）")

    return PlainTextResponse(
        content=task.subtitle_vtt,
        media_type="text/vtt",
        headers={
            "Content-Disposition": f'attachment; filename="{task.task_name}_subtitle.vtt"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get(
    "/subtitle/{task_id}/srt",
    response_class=PlainTextResponse,
    responses={
        200: {"content": {"text/plain": {}}},
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
async def get_subtitle_srt(task_id: str):
    """获取 SRT 格式字幕（可下载）"""
    if task_manager is None:
        raise HTTPException(status_code=503, detail="服务尚未初始化")

    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    if task.status == TaskStatus.ERROR:
        raise HTTPException(status_code=400, detail=f"任务处理失败: {task.error_message}")
    if task.status != TaskStatus.DONE:
        raise HTTPException(status_code=400, detail=f"任务尚未完成（当前状态: {task.status.value}）")

    return PlainTextResponse(
        content=task.subtitle_srt,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{task.task_name}_subtitle.srt"',
            "Cache-Control": "public, max-age=3600",
        },
    )


# ─── 任务列表 ─────────────────────────────────────

@router.get("/subtitle/list")
async def list_tasks(limit: int = 20, status: Optional[str] = None):
    """列出最近的任务"""
    if task_manager is None:
        raise HTTPException(status_code=503, detail="服务尚未初始化")

    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")

    tasks = task_manager.list_tasks(limit=limit, status_filter=status_filter)
    return {"tasks": tasks, "total": len(tasks)}


# ─── 取消任务 ─────────────────────────────────────

@router.post("/subtitle/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消正在处理的任务"""
    if task_manager is None:
        raise HTTPException(status_code=503, detail="服务尚未初始化")

    success = task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="无法取消任务（可能已完成、已失败或不存在）",
        )
    return {"message": "任务已取消", "task_id": task_id}


# ═══════════════════════════════════════════════════
# 后台处理管道
# ═══════════════════════════════════════════════════

def _process_subtitle_task(task_id: str) -> None:
    """后台处理字幕生成任务（在独立线程中运行）"""
    if task_manager is None:
        return

    task = task_manager.get_task(task_id)
    if task is None:
        return

    task_manager.start_task(task_id)

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    srt_path: Optional[Path] = None
    video_path: Optional[Path] = None

    try:
        # ── 步骤 0: 获取视频文件 ──────────────────
        if task.video_url:
            # 从 URL 下载
            task_manager.update_task(
                task_id, TaskStatus.DOWNLOADING, 5,
                "正在下载视频...",
            )
            video_path = _download_video(task.video_url, output_dir)
            if video_path is None:
                task_manager.fail_task(
                    task_id,
                    "视频下载失败，请确认 URL 有效且 yt-dlp 已安装",
                )
                return
        elif task.video_file_path:
            video_path = Path(task.video_file_path)
        else:
            task_manager.fail_task(task_id, "未提供视频 URL 或文件")
            return

        task_manager.update_task(
            task_id, TaskStatus.DOWNLOADING, 15,
            f"视频已就绪: {video_path.name}",
        )

        # ── 步骤 1: 语音识别 ──────────────────────
        task_manager.update_task(
            task_id, TaskStatus.TRANSCRIBING, 20,
            "正在语音识别...",
        )

        from src.asr.transcriber import WhisperTranscriber

        # 加载配置
        import yaml
        cfg_path = Path("config/settings.yaml")
        config = {}
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        asr_cfg = config.get("asr", {})
        transcriber = WhisperTranscriber(
            model_size=asr_cfg.get("model_size", "small"),
            device=asr_cfg.get("device", "cpu"),
            compute_type=asr_cfg.get("compute_type", "int8"),
            cpu_threads=asr_cfg.get("cpu_threads", 4),
        )

        result = transcriber.transcribe(
            media_path=video_path,
            output_dir=str(output_dir),
            language=task.source_language,
            beam_size=asr_cfg.get("beam_size", 5),
            vad_filter=asr_cfg.get("vad_filter", True),
        )

        srt_path = result.srt_path
        segment_count = len(result.segments)
        task.segment_count = segment_count

        task_manager.update_task(
            task_id, TaskStatus.TRANSCRIBING, 50,
            f"语音识别完成，共 {segment_count} 段",
        )

        # ── 步骤 2: 翻译 ──────────────────────────
        if task.source_language != task.target_language:
            task_manager.update_task(
                task_id, TaskStatus.TRANSLATING, 55,
                f"正在翻译 {task.source_language} → {task.target_language}...",
            )

            srt_content = srt_path.read_text(encoding="utf-8")

            translator = create_translator(
                provider=task.translation_provider,
            )

            tcfg = config.get("translation", {})
            batch_size = tcfg.get("batch_size", 5)

            translated_srt = translator.translate_srt(
                srt_content=srt_content,
                source_lang=task.source_language,
                target_lang=task.target_language,
                batch_size=batch_size,
            )

            # 保存翻译后的 SRT
            translated_srt_path = output_dir / f"{srt_path.stem}_translated.srt"
            translated_srt_path.write_text(translated_srt, encoding="utf-8")
            srt_path = translated_srt_path

            task_manager.update_task(
                task_id, TaskStatus.TRANSLATING, 80,
                "翻译完成",
            )

        # ── 步骤 3: 生成字幕 ───────────────────────
        task_manager.update_task(
            task_id, TaskStatus.GENERATING, 85,
            "正在生成字幕文件...",
        )

        final_srt = srt_path.read_text(encoding="utf-8")
        vtt_content = srt_to_vtt(final_srt)

        # 保存 VTT 文件
        vtt_path = output_dir / f"{srt_path.stem}.vtt"
        vtt_path.write_text(vtt_content, encoding="utf-8")

        # 获取视频时长（粗略）
        duration = _get_video_duration(video_path)

        # ── 完成 ──────────────────────────────────
        task_manager.complete_task(
            task_id=task_id,
            subtitle_vtt=vtt_content,
            subtitle_srt=final_srt,
            video_title=video_path.stem,
            duration_seconds=duration,
            segment_count=segment_count,
        )

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        task_manager.fail_task(task_id, error_msg)

    finally:
        # 清理临时视频文件（如果是下载的）
        if video_path and task.video_url and video_path.exists():
            try:
                video_path.unlink()
            except Exception:
                pass


def _download_video(url: str, output_dir: Path) -> Optional[Path]:
    """使用 yt-dlp 下载视频，返回视频文件路径"""
    try:
        import yt_dlp
    except ImportError:
        return None

    output_dir = output_dir / "downloads"
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # 处理可能的扩展名变化
            path = Path(filename)
            if not path.exists():
                # 尝试查找下载的文件
                files = list(output_dir.glob(f"{info['title']}.*"))
                if files:
                    path = files[0]
                else:
                    return None

            return path

    except Exception:
        return None


def _get_video_duration(video_path: Path) -> Optional[int]:
    """获取视频时长（秒）"""
    try:
        import subprocess
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(float(result.stdout.strip()))
    except Exception:
        pass
    return None
