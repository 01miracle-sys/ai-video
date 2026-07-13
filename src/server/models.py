"""
数据模型 - Pydantic 请求/响应模型
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    GENERATING = "generating"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class SubtitleRequest(BaseModel):
    """提交字幕生成请求"""
    video_url: str = Field(
        ..., description="视频 URL 地址（YouTube/B站等）"
    )
    source_language: str = Field(
        default="ja", description="源语言代码 (ja/en/zh...)"
    )
    target_language: str = Field(
        default="zh", description="目标语言代码 (zh/en...)"
    )
    translation_provider: Optional[str] = Field(
        default=None, description="翻译后端 (ollama/api，留空使用配置默认)"
    )
    task_name: Optional[str] = Field(
        default=None, description="任务自定义名称"
    )


class FileUploadRequest(BaseModel):
    """文件上传模式（用 multipart/form-data 上传视频）"""
    source_language: str = Field(default="ja")
    target_language: str = Field(default="zh")
    translation_provider: Optional[str] = None


class TaskProgress(BaseModel):
    """任务进度响应"""
    task_id: str
    status: TaskStatus
    progress: int = Field(..., ge=0, le=100, description="进度百分比 0-100")
    message: str = Field(default="", description="当前状态描述")
    video_title: Optional[str] = None
    error_message: Optional[str] = None


class TaskResult(BaseModel):
    """任务结果 - 字幕就绪"""
    task_id: str
    status: TaskStatus = TaskStatus.DONE
    subtitle_vtt: str = Field(default="", description="WebVTT 字幕内容")
    subtitle_srt: str = Field(default="", description="SRT 字幕内容")
    duration_seconds: Optional[int] = None
    segment_count: Optional[int] = None


class TaskSubmitResponse(BaseModel):
    """提交任务后立即返回"""
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str = "任务已提交，请轮询 /status 获取进度"


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    version: str = "1.0.0"
    ollama_connected: bool = False
    active_tasks: int = 0
