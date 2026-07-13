"""
异步任务管理器 - 管理字幕生成任务的进度、状态、生命周期

功能:
  - 任务队列管理（同时最多处理 max_concurrent_tasks 个任务）
  - 进度上报（0-100%）
  - 状态跟踪（pending → downloading → transcribing → translating → generating → done/error）
  - 自动清理过期任务
  - 任务结果缓存
"""

import json
import time
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import yaml

from src.server.models import TaskStatus, TaskProgress


class SubtitleTask:
    """单个字幕生成任务"""

    def __init__(
        self,
        task_id: str,
        video_url: str = "",
        video_file_path: str = "",
        source_language: str = "ja",
        target_language: str = "zh",
        translation_provider: str = "ollama",
        task_name: str = "",
    ) -> None:
        self.task_id = task_id
        self.video_url = video_url
        self.video_file_path = video_file_path
        self.source_language = source_language
        self.target_language = target_language
        self.translation_provider = translation_provider
        self.task_name = task_name or video_url.split("/")[-1][:30]

        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = "任务已创建"
        self.error_message: Optional[str] = None

        self.video_title: Optional[str] = None
        self.subtitle_vtt: str = ""
        self.subtitle_srt: str = ""
        self.duration_seconds: Optional[int] = None
        self.segment_count: Optional[int] = None

        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at: Optional[datetime] = None

    def update(self, status: TaskStatus, progress: int, message: str) -> None:
        """更新任务状态"""
        self.status = status
        self.progress = progress
        self.message = message
        self.updated_at = datetime.now()
        if status in (TaskStatus.DONE, TaskStatus.ERROR, TaskStatus.CANCELLED):
            self.completed_at = datetime.now()

    def to_progress(self) -> TaskProgress:
        """转为进度响应模型"""
        return TaskProgress(
            task_id=self.task_id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            video_title=self.video_title,
            error_message=self.error_message,
        )

    def is_expired(self, cleanup_hours: int = 24) -> bool:
        """检查任务是否过期"""
        if self.completed_at is None:
            return False
        return datetime.now() - self.completed_at > timedelta(hours=cleanup_hours)

    def to_dict(self) -> dict:
        """序列化为字典（用于持久化）"""
        return {
            "task_id": self.task_id,
            "video_url": self.video_url,
            "video_file_path": self.video_file_path,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "translation_provider": self.translation_provider,
            "task_name": self.task_name,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "error_message": self.error_message,
            "video_title": self.video_title,
            "subtitle_vtt": self.subtitle_vtt,
            "subtitle_srt": self.subtitle_srt,
            "duration_seconds": self.duration_seconds,
            "segment_count": self.segment_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskManager:
    """任务管理器（线程安全）"""

    def __init__(
        self,
        max_concurrent: int = 2,
        cleanup_hours: int = 24,
        data_dir: str | Path = "outputs/tasks",
    ) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, SubtitleTask] = {}
        self._running_count = 0
        self.max_concurrent = max_concurrent
        self.cleanup_hours = cleanup_hours
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 恢复未完成的任务
        self._load_tasks()

    # ─── 任务 CRUD ───────────────────────────────

    def create_task(
        self,
        video_url: str = "",
        video_file_path: str = "",
        source_language: str = "ja",
        target_language: str = "zh",
        translation_provider: str = "ollama",
        task_name: str = "",
    ) -> SubtitleTask:
        """创建新任务"""
        task_id = uuid.uuid4().hex[:12]
        task = SubtitleTask(
            task_id=task_id,
            video_url=video_url,
            video_file_path=video_file_path,
            source_language=source_language,
            target_language=target_language,
            translation_provider=translation_provider,
            task_name=task_name,
        )
        with self._lock:
            self._tasks[task_id] = task
            self._save_task(task)
        return task

    def get_task(self, task_id: str) -> Optional[SubtitleTask]:
        """获取任务"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_task_progress(self, task_id: str) -> Optional[TaskProgress]:
        """获取任务进度"""
        task = self.get_task(task_id)
        if task is None:
            return None
        return task.to_progress()

    def update_task(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int,
        message: str,
    ) -> Optional[SubtitleTask]:
        """更新任务状态"""
        task = self.get_task(task_id)
        if task is None:
            return None
        task.update(status, progress, message)
        with self._lock:
            self._save_task(task)
        return task

    def complete_task(
        self,
        task_id: str,
        subtitle_vtt: str,
        subtitle_srt: str,
        video_title: str = "",
        duration_seconds: Optional[int] = None,
        segment_count: Optional[int] = None,
    ) -> Optional[SubtitleTask]:
        """标记任务完成并保存结果"""
        task = self.get_task(task_id)
        if task is None:
            return None
        task.subtitle_vtt = subtitle_vtt
        task.subtitle_srt = subtitle_srt
        task.video_title = video_title
        task.duration_seconds = duration_seconds
        task.segment_count = segment_count
        task.update(TaskStatus.DONE, 100, "字幕生成完成")
        with self._lock:
            self._running_count -= 1
            self._save_task(task)
        return task

    def fail_task(self, task_id: str, error_message: str) -> Optional[SubtitleTask]:
        """标记任务失败"""
        task = self.get_task(task_id)
        if task is None:
            return None
        task.error_message = error_message
        task.update(TaskStatus.ERROR, 0, f"失败: {error_message[:100]}")
        with self._lock:
            self._running_count -= 1
            self._save_task(task)
        return task

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.get_task(task_id)
        if task is None:
            return False
        if task.status in (TaskStatus.DONE, TaskStatus.ERROR, TaskStatus.CANCELLED):
            return False
        task.update(TaskStatus.CANCELLED, 0, "任务已取消")
        with self._lock:
            self._save_task(task)
        return True

    def can_accept_task(self) -> bool:
        """检查是否可以接受新任务"""
        with self._lock:
            return self._running_count < self.max_concurrent

    def start_task(self, task_id: str) -> bool:
        """标记任务开始运行"""
        task = self.get_task(task_id)
        if task is None:
            return False
        with self._lock:
            self._running_count += 1
        return True

    # ─── 列表查询 ───────────────────────────────

    def list_tasks(
        self, limit: int = 20, status_filter: Optional[TaskStatus] = None
    ) -> list[TaskProgress]:
        """列出任务"""
        with self._lock:
            tasks = list(self._tasks.values())

        # 排序：最新的在前
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        result = []
        for task in tasks:
            if status_filter and task.status != status_filter:
                continue
            result.append(task.to_progress())
            if len(result) >= limit:
                break
        return result

    def active_count(self) -> int:
        """当前活跃任务数"""
        with self._lock:
            return self._running_count

    # ─── 清理 ────────────────────────────────────

    def cleanup_expired(self) -> int:
        """清理过期任务，返回清理数量"""
        with self._lock:
            expired = [
                tid
                for tid, task in self._tasks.items()
                if task.is_expired(self.cleanup_hours)
            ]
            for tid in expired:
                task = self._tasks.pop(tid)
                self._delete_task_file(task)
            return len(expired)

    # ─── 持久化 ──────────────────────────────────

    def _task_file(self, task_id: str) -> Path:
        return self.data_dir / f"{task_id}.json"

    def _save_task(self, task: SubtitleTask) -> None:
        """保存任务到文件"""
        filepath = self._task_file(task.task_id)
        try:
            filepath.write_text(
                json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # 持久化失败不影响运行

    def _delete_task_file(self, task: SubtitleTask) -> None:
        """删除任务文件"""
        filepath = self._task_file(task.task_id)
        if filepath.exists():
            try:
                filepath.unlink()
            except Exception:
                pass

    def _load_tasks(self) -> None:
        """从磁盘恢复未过期的任务"""
        if not self.data_dir.exists():
            return
        for filepath in self.data_dir.glob("*.json"):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                task = SubtitleTask(
                    task_id=data["task_id"],
                    video_url=data.get("video_url", ""),
                    video_file_path=data.get("video_file_path", ""),
                    source_language=data.get("source_language", "ja"),
                    target_language=data.get("target_language", "zh"),
                    translation_provider=data.get("translation_provider", "ollama"),
                    task_name=data.get("task_name", ""),
                )
                task.status = TaskStatus(data.get("status", "pending"))
                task.progress = data.get("progress", 0)
                task.message = data.get("message", "")
                task.error_message = data.get("error_message")
                task.video_title = data.get("video_title")
                task.subtitle_vtt = data.get("subtitle_vtt", "")
                task.subtitle_srt = data.get("subtitle_srt", "")
                task.duration_seconds = data.get("duration_seconds")
                task.segment_count = data.get("segment_count")

                # 跳过过期任务
                if task.is_expired(self.cleanup_hours):
                    filepath.unlink()
                    continue

                # 如果任务未完成，重置为 pending
                if task.status in (
                    TaskStatus.DOWNLOADING,
                    TaskStatus.TRANSCRIBING,
                    TaskStatus.TRANSLATING,
                    TaskStatus.GENERATING,
                ):
                    task.status = TaskStatus.PENDING
                    task.progress = 0
                    task.message = "任务已恢复（待处理）"

                self._tasks[task.task_id] = task

            except Exception:
                # 损坏的文件，安全清理
                try:
                    filepath.unlink()
                except Exception:
                    pass
