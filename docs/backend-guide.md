# Milo-Cut Backend Implementation Guide

基于 Python 3.11+ / PyWebVue / FFmpeg 的后端架构指南。本指南基于对 **PyWebVue 框架源码** 和 **ff-intelligent-neo 参考项目后端** 的深度分析编写，所有模式和约定均有实际代码依据。

---

## 1. 架构总览

```
Milo-Cut Desktop App
|
|-- main.py                    -- 入口：创建 App，注册 Bridge，启动窗口
|
|-- pywebvue/                  -- 框架层（已有，直接使用）
|   |-- app.py                 -- App 类：窗口生命周期、tick 轮询、dev/prod 路径
|   |-- bridge.py              -- Bridge 基类：@expose 装饰器、事件队列、handler 任务系统
|   |-- __init__.py            -- 导出 App, Bridge, expose
|
|-- core/                      -- 业务层
|   |-- api.py                 -- MiloCutApi(Bridge)：所有 @expose 方法
|   |-- events.py              -- 事件名常量（前后端共享）
|   |-- models.py              -- frozen dataclass 数据模型
|   |-- task_manager.py        -- 统一任务管理器
|   |-- services/
|   |   |-- ffmpeg_service.py  -- FFmpeg/ffprobe 进程封装
|   |   |-- audio_service.py   -- 音频提取（WAV 16kHz mono）
|   |   |-- silence_service.py -- 静音检测（silencedetect）
|   |   |-- analysis_service.py -- 多层分析引擎编排
|   |   |-- subtitle_service.py -- SRT 导入/解析/CRUD
|   |   |-- export_service.py  -- 多格式导出（精确/快速双模式）
|   |   |-- project_service.py -- 项目文件管理（JSON 持久化）
|   |   |-- preview_service.py -- 代理文件生成（P1）
|   |   |-- vad_service.py     -- VAD 增强检测（P1）
|   |   |-- asr_service.py     -- ASR 转写抽象层（P1）
|   |-- config.py              -- 应用设置（FFmpeg 路径等）
|   |-- paths.py               -- 数据目录、缓存目录路径
|   |-- logging.py             -- loguru 日志配置
```

---

## 2. PyWebVue Bridge 核心机制

### 2.1 @expose 装饰器

所有暴露给前端的方法必须使用 `@expose` 装饰。装饰器自动提供 try/except 包裹：

```python
from pywebvue import Bridge, expose

class MiloCutApi(Bridge):
    @expose
    def create_project(self, name: str, media_path: str) -> dict:
        # 正常返回
        return {"success": True, "data": {...}}

    @expose
    def risky_operation(self) -> dict:
        raise ValueError("something went wrong")
        # 自动变为: {"success": False, "error": "Internal error", "code": "INTERNAL_ERROR"}
```

**关键行为：**
- 生产模式（默认）：异常信息隐藏，只返回 "Internal error"
- 调试模式（`Bridge(debug=True)`）：返回真实异常信息
- 所有方法签名建议添加类型注解
- 返回值必须是 `dict`，约定格式 `{"success": bool, "data": ..., "error": ...}`

### 2.2 事件推送

```python
# 从任意线程推送事件（线程安全）
self._emit("task:progress", {"task_id": "xxx", "progress": 50, "message": "..."})
```

事件在下一个 `tick()` 循环（50ms 间隔）中被刷新到前端。前端通过 `onEvent()` 接收。

### 2.3 Bridge-thread 任务执行

需要从后台线程访问 DOM 相关操作时使用（MVP 阶段通常不需要）：

```python
# 注册 handler
self.register_handler("update_dom", my_dom_handler)

# 从后台线程调用（阻塞等待结果）
result = self.run_on_bridge("update_dom", args=some_data, timeout=30.0)
```

### 2.4 拖拽文件

PyWebVue 内置文件拖拽支持，前端通过 `get_dropped_files()` 获取路径：

```python
# 后端自动处理 drop 事件，路径存入 _dropped_paths
# 前端调用后清空缓冲区
@expose
def get_dropped_files(self) -> dict:
    with self._drop_lock:
        paths = list(self._dropped_paths)
        self._dropped_paths.clear()
    return {"success": True, "data": paths}
```

---

## 3. 入口文件 main.py

参考 ff-intelligent-neo 的模式：

```python
# main.py
"""Milo-Cut - AI video rough-cut preprocessor."""

from __future__ import annotations

import atexit
import sys
import threading
from pathlib import Path

from pywebvue import App, Bridge, expose
from core.logging import get_logger, setup_frontend_sink
from core.config import load_settings

logger = get_logger()


class MiloCutApi(Bridge):

    def __init__(self) -> None:
        super().__init__()
        self._loguru_initialized = False

    def _ensure_loguru(self) -> None:
        """Setup loguru frontend sink once the bridge emit is available."""
        if self._loguru_initialized:
            return
        self._loguru_initialized = True
        setup_frontend_sink(self._emit)

    # Lazy-loaded services (thread-safe)
    @property
    def _project_service(self):
        from core.services.project_service import ProjectService
        if not hasattr(self, "_project_svc"):
            self._project_svc = ProjectService(self._emit)
        return self._project_svc

    @property
    def _task_manager(self):
        from core.task_manager import TaskManager
        if not hasattr(self, "_task_mgr"):
            self._task_mgr = TaskManager(self._emit)
        return self._task_mgr

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    @expose
    def get_app_info(self) -> dict:
        try:
            from core.config import get_app_info
            return {"success": True, "data": get_app_info()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # File dialogs (via pywebview)
    # ------------------------------------------------------------------

    @expose
    def select_files(self, file_types: list | None = None) -> dict:
        try:
            import webview
            kwargs: dict = {
                "dialog_type": webview.FileDialog.OPEN,
                "allow_multiple": True,
            }
            if file_types:
                kwargs["file_types"] = tuple(file_types)
            result = self._window.create_file_dialog(**kwargs)
            if result:
                return {"success": True, "data": list(result)}
            return {"success": True, "data": []}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @expose
    def select_file(self, file_types: list | None = None) -> dict:
        try:
            import webview
            kwargs: dict = {"dialog_type": webview.FileDialog.OPEN}
            if file_types:
                kwargs["file_types"] = tuple(file_types)
            result = self._window.create_file_dialog(**kwargs)
            if result and len(result) > 0:
                return {"success": True, "data": result[0]}
            return {"success": True, "data": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @expose
    def open_folder(self, path: str) -> dict:
        try:
            import os
            import subprocess
            folder = os.path.dirname(path) if os.path.isfile(path) else path
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
            return {"success": True, "data": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Project management
    # ------------------------------------------------------------------

    @expose
    def create_project(self, name: str, media_path: str) -> dict:
        self._ensure_loguru()
        try:
            project = self._project_service.create(name, media_path)
            return {"success": True, "data": project.to_dict()}
        except Exception as exc:
            logger.exception("create_project failed")
            return {"success": False, "error": str(exc)}

    @expose
    def open_project(self, project_path: str) -> dict:
        self._ensure_loguru()
        try:
            project = self._project_service.open(project_path)
            return {"success": True, "data": project.to_dict()}
        except Exception as exc:
            logger.exception("open_project failed")
            return {"success": False, "error": str(exc)}

    @expose
    def save_project(self) -> dict:
        try:
            self._project_service.save()
            return {"success": True, "data": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def close_project(self) -> dict:
        try:
            self._project_service.close()
            return {"success": True, "data": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def get_recent_projects(self) -> dict:
        try:
            projects = self._project_service.get_recent()
            return {"success": True, "data": projects}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Unified task API
    # ------------------------------------------------------------------

    @expose
    def create_task(self, task_type: str, payload: dict) -> dict:
        self._ensure_loguru()
        try:
            task = self._task_manager.create(task_type, payload)
            return {"success": True, "data": task.to_dict()}
        except Exception as exc:
            logger.exception("create_task failed")
            return {"success": False, "error": str(exc)}

    @expose
    def start_task(self, task_id: str) -> dict:
        try:
            self._task_manager.start(task_id)
            return {"success": True, "data": None}
        except Exception as exc:
            logger.exception("start_task failed")
            return {"success": False, "error": str(exc)}

    @expose
    def cancel_task(self, task_id: str) -> dict:
        try:
            self._task_manager.cancel(task_id)
            return {"success": True, "data": None}
        except Exception as exc:
            logger.exception("cancel_task failed")
            return {"success": False, "error": str(exc)}

    @expose
    def get_task(self, task_id: str) -> dict:
        try:
            task = self._task_manager.get(task_id)
            return {"success": True, "data": task.to_dict() if task else None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def list_tasks(self) -> dict:
        try:
            tasks = self._task_manager.list_all()
            return {"success": True, "data": [t.to_dict() for t in tasks]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Subtitle editing
    # ------------------------------------------------------------------

    @expose
    def update_segment_text(self, segment_id: str, text: str) -> dict:
        try:
            self._project_service.update_segment_text(segment_id, text)
            return {"success": True, "data": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def merge_segments(self, segment_ids: list) -> dict:
        try:
            merged = self._project_service.merge_segments(segment_ids)
            return {"success": True, "data": merged}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def split_segment(self, segment_id: str, position: float) -> dict:
        try:
            result = self._project_service.split_segment(segment_id, position)
            return {"success": True, "data": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def search_replace(self, query: str, replacement: str, scope: str = "all") -> dict:
        try:
            count = self._project_service.search_replace(query, replacement, scope)
            return {"success": True, "data": {"count": count}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Edit decisions
    # ------------------------------------------------------------------

    @expose
    def mark_segments(self, segment_ids: list, action: str) -> dict:
        try:
            self._project_service.mark_segments(segment_ids, action)
            return {"success": True, "data": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def confirm_all_suggestions(self) -> dict:
        try:
            count = self._project_service.confirm_all_suggestions()
            return {"success": True, "data": {"count": count}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def reject_all_suggestions(self) -> dict:
        try:
            count = self._project_service.reject_all_suggestions()
            return {"success": True, "data": {"count": count}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def get_edit_summary(self) -> dict:
        try:
            summary = self._project_service.get_edit_summary()
            return {"success": True, "data": summary}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        if getattr(self, "_cleanup_done", False):
            return
        self._cleanup_done = True
        try:
            if hasattr(self, "_task_mgr"):
                self._task_mgr.shutdown()
            self._project_service.save()
        except Exception as exc:
            logger.error("Cleanup error: {}", exc)


if __name__ == "__main__":
    import atexit

    api = MiloCutApi()
    atexit.register(api._cleanup)
    app = App(
        api,
        title="Milo-Cut",
        width=1400,
        height=900,
        min_size=(1100, 600),
        frontend_dir="frontend_dist",
        on_closing=api._cleanup,
    )
    app.run()
```

---

## 4. 事件常量（core/events.py）

前后端共享的事件名定义，Python 和 TypeScript 各维护一份，必须保持同步：

```python
# core/events.py

# 任务生命周期
TASK_PROGRESS = "task:progress"
TASK_COMPLETED = "task:completed"
TASK_FAILED = "task:failed"

# 项目状态
PROJECT_SAVED = "project:saved"
PROJECT_DIRTY = "project:dirty"

# 分析结果
ANALYSIS_UPDATED = "analysis:updated"

# 日志转发
LOG_LINE = "log_line"
```

事件名规范：
- 使用小写字母 + 下划线，层级用冒号分隔（如 `task:progress`）
- 最长 128 字符，仅含 `[A-Za-z0-9_.:-]`

---

## 5. 数据模型（core/models.py）

遵循 ff-intelligent-neo 验证的模式：**配置用 frozen dataclass，运行状态用可变 dataclass**。

```python
# core/models.py
"""Frozen dataclasses for type-safe data transfer."""

from __future__ import annotations

import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Task types (MVP / P1 分离)
# ---------------------------------------------------------------------------

TaskType = Literal[
    # MVP
    "silence_detection",
    "filler_detection",
    "error_detection",
    "full_analysis",
    "export_video",
    "export_subtitle",
    # P1
    "transcription",
    "repetition_detection",
    "vad_analysis",
    "waveform_generation",
    "proxy_generation",
    "export_timeline",
]

TaskStatus = Literal["queued", "running", "completed", "failed", "cancelled"]

VALID_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    "queued": {"running", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "failed": {"queued"},
    "cancelled": {"queued"},
    "completed": set(),  # terminal
}


# ---------------------------------------------------------------------------
# Task entity (mutable -- status/progress updated at runtime)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskProgress:
    percent: float = 0.0
    message: str = ""

    def to_dict(self) -> dict:
        return {"percent": self.percent, "message": self.message}


@dataclass
class MiloTask:
    """Unified task for all long-running operations."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: str = ""
    status: str = "queued"
    progress: TaskProgress = field(default_factory=TaskProgress)
    payload: dict = field(default_factory=dict)
    result: Any = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str = ""
    completed_at: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set_progress(self, progress: TaskProgress) -> None:
        with self.lock:
            self.progress = progress

    def can_transition(self, new_status: str) -> bool:
        return new_status in VALID_TASK_TRANSITIONS.get(self.status, set())

    def transition(self, new_status: str) -> str:
        if not self.can_transition(new_status):
            raise ValueError(f"Invalid transition: {self.status} -> {new_status}")
        old = self.status
        self.status = new_status
        if new_status == "running" and not self.started_at:
            self.started_at = datetime.now().isoformat()
        if new_status in ("completed", "failed", "cancelled"):
            self.completed_at = datetime.now().isoformat()
        return old

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "progress": self.progress.to_dict(),
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
```

### 5.1 项目数据模型

项目模型直接映射 `project.json` schema（见 PRD Section 10）：

```python
# core/models.py (续)

@dataclass(frozen=True)
class MediaInfo:
    path: str = ""
    media_hash: str = ""
    duration: float = 0.0
    format: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    audio_channels: int = 0
    sample_rate: int = 0
    bit_rate: int = 0
    proxy_path: str | None = None
    waveform_path: str | None = None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> MediaInfo: ...


@dataclass(frozen=True)
class Word:
    word: str = ""
    start: float = 0.0
    end: float = 0.0
    confidence: float = 0.0


@dataclass
class Segment:
    """Mutable: text, start, end can be edited by user."""
    id: str = ""
    version: int = 1
    type: str = "subtitle"  # "subtitle" | "silence"
    start: float = 0.0
    end: float = 0.0
    text: str = ""
    words: list = field(default_factory=list)
    speaker: str | None = None
    dirty_flags: dict = field(default_factory=lambda: {
        "textChanged": False, "timeChanged": False, "analysisStale": False
    })

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> Segment: ...


@dataclass(frozen=True)
class AnalysisResult:
    id: str = ""
    type: str = ""  # silence | filler | error | repetition
    segment_ids: list = field(default_factory=list)
    confidence: float = 0.0
    detail: str = ""


@dataclass(frozen=True)
class EditDecision:
    id: str = ""
    start: float = 0.0
    end: float = 0.0
    action: str = "delete"  # delete | keep
    source: str = ""  # auto_silence | auto_filler | auto_error | user
    analysis_id: str | None = None
    status: str = "pending"  # pending | confirmed | rejected
    priority: int = 100  # auto=100, user=200
```

---

## 6. 统一任务管理器（core/task_manager.py）

参考 ff-intelligent-neo 的 TaskQueue + TaskRunner 模式，为 Milo-Cut 适配统一任务 API：

```python
# core/task_manager.py
"""Unified task manager for all long-running operations."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from core.models import MiloTask, TaskProgress, TaskStatus
from core.events import TASK_PROGRESS, TASK_COMPLETED, TASK_FAILED
from core.logging import get_logger

logger = get_logger()


class TaskManager:
    """Manages all background tasks with thread pool execution."""

    def __init__(self, emit: Callable) -> None:
        self._emit = emit
        self._tasks: dict[str, MiloTask] = {}
        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._handlers: dict[str, Callable] = {}
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register task type -> handler function mapping."""
        from core.services.silence_service import run_silence_detection
        from core.services.analysis_service import run_full_analysis
        from core.services.export_service import run_export_video

        self._handlers = {
            "silence_detection": run_silence_detection,
            "full_analysis": run_full_analysis,
            "export_video": run_export_video,
            "export_subtitle": run_export_video,  # TODO: separate handler
            # P1 handlers registered lazily
        }

    def start(self, max_workers: int = 1) -> None:
        if self._executor is not None:
            return
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def shutdown(self) -> None:
        for evt in self._cancel_events.values():
            evt.set()
        self._cancel_events.clear()
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, task_type: str, payload: dict) -> MiloTask:
        task = MiloTask(type=task_type, payload=payload)
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> MiloTask | None:
        return self._tasks.get(task_id)

    def list_all(self) -> list[MiloTask]:
        with self._lock:
            return list(self._tasks.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if not task.can_transition("running"):
            raise ValueError(f"Invalid transition: {task.status} -> running")

        handler = self._handlers.get(task.type)
        if handler is None:
            task.transition("failed")
            task.error = f"No handler for task type: {task.type}"
            self._emit(TASK_FAILED, {"task_id": task_id, "error": task.error, "code": "NO_HANDLER"})
            return

        cancel_event = threading.Event()
        self._cancel_events[task_id] = cancel_event

        task.transition("running")
        self._emit(TASK_PROGRESS, {
            "task_id": task_id, "progress": 0, "message": "Starting...",
        })

        assert self._executor is not None
        self._executor.submit(
            self._run_handler, task, handler, cancel_event,
        )

    def cancel(self, task_id: str) -> None:
        evt = self._cancel_events.get(task_id)
        if evt:
            evt.set()
        task = self._tasks.get(task_id)
        if task and task.status in ("queued", "running"):
            task.transition("cancelled")
            self._emit(TASK_PROGRESS, {
                "task_id": task_id, "progress": task.progress.percent,
                "message": "Cancelled",
            })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_handler(
        self,
        task: MiloTask,
        handler: Callable,
        cancel_event: threading.Event,
    ) -> None:
        task_id = task.id

        def on_progress(percent: float, message: str = "") -> None:
            if cancel_event.is_set():
                return
            task.set_progress(TaskProgress(percent=percent, message=message))
            self._emit(TASK_PROGRESS, {
                "task_id": task_id, "progress": percent, "message": message,
            })

        try:
            result = handler(
                task=task,
                emit=self._emit,
                progress_cb=on_progress,
                cancel_event=cancel_event,
            )
            if cancel_event.is_set():
                return
            task.result = result
            task.transition("completed")
            self._emit(TASK_COMPLETED, {"task_id": task_id, "result": result})
        except Exception as exc:
            if cancel_event.is_set():
                return
            logger.exception("Task {} failed", task_id)
            task.error = str(exc)
            task.transition("failed")
            self._emit(TASK_FAILED, {"task_id": task_id, "error": str(exc), "code": "HANDLER_ERROR"})
        finally:
            self._cancel_events.pop(task_id, None)
```

### 6.1 任务处理器签名约定

所有任务处理器遵循统一签名：

```python
def handler(
    task: MiloTask,
    emit: Callable,
    progress_cb: Callable[[float, str], None],
    cancel_event: threading.Event,
) -> Any:
    """
    Args:
        task: 任务对象，包含 payload、type 等信息
        emit: 事件推送函数 (thread-safe)
        progress_cb: 进度回调 (percent: 0-100, message: str)
        cancel_event: 取消信号，检测后应尽快退出

    Returns:
        任务结果，存储到 task.result

    Raises:
        Exception: 任务失败，自动捕获并转为 failed 状态
    """
    ...
```

---

## 7. 核心服务

### 7.1 FFmpeg 服务（core/services/ffmpeg_service.py）

FFmpeg/ffprobe 进程封装，参考 ff-intelligent-neo 的 `ffmpeg_runner.py`：

```python
# core/services/ffmpeg_service.py
"""FFmpeg/ffprobe process wrapper."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.ffmpeg_setup import get_ffmpeg_path, get_ffprobe_path
from core.logging import get_logger

logger = get_logger()


@dataclass(frozen=True)
class MediaProbeResult:
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    format: str = ""
    audio_channels: int = 0
    sample_rate: int = 0
    bit_rate: int = 0
    codec: str = ""


def probe_media(file_path: str) -> MediaProbeResult:
    """Probe media file with ffprobe."""
    ffprobe = get_ffprobe_path()
    if not ffprobe:
        raise RuntimeError("ffprobe not found")

    cmd = [
        ffprobe, "-v", "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=codec_name,width,height,"
        "r_frame_rate,channels,sample_rate:stream=codec_type=video",
        "-of", "json",
        file_path,
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    import json
    data = json.loads(result.stdout)
    # Parse result into MediaProbeResult...
    return _parse_probe(data)


def run_ffmpeg(
    args: list[str],
    cancel_event: "threading.Event | None" = None,
    on_progress: "Callable[[float, str], None] | None" = None,
) -> tuple[bool, str]:
    """Run FFmpeg with progress monitoring and cancellation support.

    Returns (success, error_message).
    """
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )

    try:
        for line in proc.stdout:
            if cancel_event and cancel_event.is_set():
                proc.terminate()
                return False, "Cancelled"

            # Parse FFmpeg progress output (time=XX:XX:XX.XX)
            if on_progress and "time=" in line:
                # Parse progress from stderr output
                ...
    except Exception:
        proc.kill()

    proc.wait()
    if proc.returncode == 0:
        return True, ""
    return False, f"FFmpeg exited with code {proc.returncode}"
```

### 7.2 静音检测服务（core/services/silence_service.py）

```python
# core/services/silence_service.py
"""Silence detection using FFmpeg silencedetect filter."""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Callable

from core.ffmpeg_setup import get_ffmpeg_path
from core.logging import get_logger

logger = get_logger()


def run_silence_detection(
    task: "MiloTask",
    emit: Callable,
    progress_cb: Callable[[float, str], None],
    cancel_event: "threading.Event",
) -> list[dict]:
    """Run silence detection on project audio.

    Uses FFmpeg silencedetect filter.
    Returns list of silence segments: [{"start": float, "end": float, "duration": float}]
    """
    from core.services.project_service import ProjectService
    project = ProjectService.instance()

    media_path = project.media.path
    min_duration = task.payload.get("min_duration", 1.0)  # seconds
    noise_tolerance = task.payload.get("noise_tolerance", -30)  # dB

    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found")

    # Extract audio first if needed
    audio_path = project.audio_path or _extract_audio(media_path)

    cmd = [
        ffmpeg, "-i", audio_path,
        "-af", f"silencedetect=noise={noise_tolerance}d:min_duration={min_duration}s",
        "-f", "null", "-",
    ]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, text=True,
        creationflags=creationflags,
    )

    silences = []
    duration = 0.0
    time_re = re.compile(r"silence_start:\s*([\d.]+)")
    end_re = re.compile(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)")

    try:
        # Read total duration first line
        for line in proc.stderr:
            if cancel_event.is_set():
                proc.terminate()
                return silences

            # Parse duration from FFmpeg output
            dur_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
            if dur_match:
                h, m, s, ms = dur_match.groups()
                duration = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100

            start_match = time_re.search(line)
            if start_match:
                start = float(start_match.group(1))

            end_match = end_re.search(line)
            if end_match:
                end = float(end_match.group(1))
                dur = float(end_match.group(2))
                silences.append({
                    "start": start,
                    "end": end,
                    "duration": dur,
                    "confidence": 0.95,
                })
                # Estimate progress
                if duration > 0:
                    pct = min(end / duration * 100, 99)
                    progress_cb(pct, f"Detected silence at {end:.1f}s")

    except Exception as exc:
        proc.kill()
        raise

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"silencedetect failed with code {proc.returncode}")

    progress_cb(100, f"Found {len(silences)} silence segments")
    return silences
```

### 7.3 字幕服务（core/services/subtitle_service.py）

```python
# core/services/subtitle_service.py
"""SRT subtitle import and parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedSubtitle:
    index: int
    start: float
    end: float
    text: str


def parse_srt(content: str) -> list[ParsedSubtitle]:
    """Parse SRT subtitle content into structured segments."""
    blocks = re.split(r"\n\s*\n", content.strip())
    results = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # Index line
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue

        # Time line: 00:00:01,000 --> 00:00:03,000
        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1].strip(),
        )
        if not time_match:
            continue

        start = (
            int(time_match.group(1)) * 3600
            + int(time_match.group(2)) * 60
            + int(time_match.group(3))
            + int(time_match.group(4)) / 1000
        )
        end = (
            int(time_match.group(5)) * 3600
            + int(time_match.group(6)) * 60
            + int(time_match.group(7))
            + int(time_match.group(8)) / 1000
        )

        # Text (may be multi-line, join with space)
        text = " ".join(line.strip() for line in lines[2:] if line.strip())
        text = re.sub(r"<[^>]+>", "", text)  # Remove HTML tags

        results.append(ParsedSubtitle(index=index, start=start, end=end, text=text))

    return results


def validate_srt(content: str, video_duration: float) -> list[str]:
    """Validate SRT content, return list of warning/error messages."""
    issues = []
    subs = parse_srt(content)

    if not subs:
        issues.append("No valid subtitles found")
        return issues

    # Check index continuity
    for i, sub in enumerate(subs):
        if sub.index != i + 1:
            issues.append(f"Non-sequential index at position {i}: expected {i+1}, got {sub.index}")

    # Check duration mismatch
    if video_duration > 0:
        total_sub = subs[-1].end
        ratio = total_sub / video_duration
        if ratio < 0.9 or ratio > 1.1:
            issues.append(
                f"Subtitle duration ({total_sub:.1f}s) "
                f"differs from video duration ({video_duration:.1f}s) by more than 10%"
            )

    # Check for negative durations
    for sub in subs:
        if sub.end <= sub.start:
            issues.append(f"Subtitle #{sub.index} has non-positive duration")

    return issues


def parse_srt_file(file_path: str) -> list[ParsedSubtitle]:
    """Read and parse an SRT file."""
    path = Path(file_path)
    content = path.read_text(encoding="utf-8-sig")  # Handle BOM
    return parse_srt(content)
```

### 7.4 导出服务（core/services/export_service.py）

```python
# core/services/export_service.py
"""Video export with precise and fast modes."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Callable

from core.ffmpeg_setup import get_ffmpeg_path
from core.logging import get_logger

logger = get_logger()


def run_export_video(
    task: "MiloTask",
    emit: Callable,
    progress_cb: Callable[[float, str], None],
    cancel_event: "threading.Event",
) -> dict:
    """Export video with confirmed edits removed.

    payload expects:
      - mode: "precise" | "fast"
      - output_path: str
    """
    from core.services.project_service import ProjectService
    project = ProjectService.instance()

    mode = task.payload.get("mode", "precise")
    output_path = task.payload.get("output_path", "")
    media_path = project.media.path

    # Get keep segments (gaps between confirmed deletes)
    keep_segments = _compute_keep_segments(project)
    if not keep_segments:
        raise ValueError("No segments to export (all content marked for deletion)")

    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    if mode == "precise":
        result_path = _export_precise(
            ffmpeg, media_path, keep_segments, output_path,
            cancel_event, progress_cb, creationflags,
        )
    else:
        result_path = _export_fast(
            ffmpeg, media_path, keep_segments, output_path,
            cancel_event, progress_cb, creationflags,
        )

    return {"output_path": result_path, "mode": mode}


def _compute_keep_segments(project) -> list[tuple[float, float]]:
    """Compute segments to keep from edit decisions."""
    edits = [e for e in project.edits if e.action == "delete" and e.status == "confirmed"]
    edits.sort(key=lambda e: e.start)

    if not edits:
        return [(0, project.media.duration)]

    keeps = []
    prev_end = 0.0

    for edit in edits:
        if edit.start > prev_end:
            keeps.append((prev_end, edit.start))
        prev_end = max(prev_end, edit.end)

    if prev_end < project.media.duration:
        keeps.append((prev_end, project.media.duration))

    return keeps


def _export_precise(
    ffmpeg: str, media_path: str, keeps: list, output_path: str,
    cancel_event, progress_cb, creationflags: int,
) -> str:
    """Re-encode mode: extract each kept segment, concat them."""
    progress_cb(5, "Building concat segments...")

    # Step 1: Extract each kept segment to temp files
    temp_dir = tempfile.mkdtemp(prefix="milocut_")
    segment_files = []

    try:
        for i, (start, end) in enumerate(keeps):
            if cancel_event.is_set():
                raise RuntimeError("Cancelled")

            seg_path = os.path.join(temp_dir, f"seg_{i:04d}.mp4")
            cmd = [
                ffmpeg, "-ss", str(start), "-to", str(end),
                "-i", media_path,
                "-c:v", "libx264", "-preset", "medium",
                "-c:a", "aac",
                "-y", seg_path,
            ]

            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True,
                                    creationflags=creationflags)
            proc.wait()

            if proc.returncode != 0:
                raise RuntimeError(f"Segment {i} encoding failed")

            segment_files.append(seg_path)
            pct = 10 + (i / len(keeps)) * 70
            progress_cb(pct, f"Encoded segment {i+1}/{len(keeps)}")

        # Step 2: Create concat list
        list_path = os.path.join(temp_dir, "concat.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for sf in segment_files:
                f.write(f"file '{sf}'\n")

        # Step 3: Concat all segments
        progress_cb(85, "Concatenating segments...")
        cmd = [
            ffmpeg, "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy", "-y", output_path,
        ]

        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True,
                                creationflags=creationflags)
        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError("Concat failed")

        progress_cb(100, "Export complete")
        return output_path

    finally:
        # Cleanup temp files
        for sf in segment_files:
            try:
                os.unlink(sf)
            except OSError:
                pass
        try:
            os.unlink(list_path)
        except OSError:
            pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass


def _export_fast(
    ffmpeg: str, media_path: str, keeps: list, output_path: str,
    cancel_event, progress_cb, creationflags: int,
) -> str:
    """Stream copy mode: re-mux only, fastest but keyframe-boundary imprecise.

    Uses segment-level cutting without filters. Output may have brief glitches
    at cut points that don't align with keyframes.
    """
    progress_cb(10, "Building segment list...")

    # Build concat demuxer with per-segment trimming
    concat_parts = []
    for i, (start, end) in enumerate(keeps):
        if cancel_event.is_set():
            raise RuntimeError("Cancelled")
        concat_parts.append(
            f"in={media_path}:ss={start:.3f}:to={end:.3f},setpts=PTS-STARTPTS"
        )
        pct = 10 + (i / len(keeps)) * 80
        progress_cb(pct, f"Preparing segment {i+1}/{len(keeps)}")

    concat_filter = "|".join(concat_parts)
    cmd = [
        ffmpeg,
        "-i", media_path,
        "-filter_complex", concat_filter,
        "-map", "0:v", "-map", "0:a",
        "-c", "copy",
        "-y", output_path,
    ]

    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True,
                            creationflags=creationflags)
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError("Fast export failed")

    progress_cb(100, "Fast export complete")
    return output_path
```

---

## 8. 项目服务（core/services/project_service.py）

```python
# core/services/project_service.py
"""Project lifecycle: create, open, save, close."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.models import Segment, EditDecision, AnalysisResult
from core.paths import get_projects_dir
from core.logging import get_logger

logger = get_logger()

# Module-level singleton for task handlers to access
_instance: "ProjectService | None" = None


class ProjectService:
    def __init__(self, emit: Callable) -> None:
        global _instance
        _instance = self
        self._emit = emit
        self._lock = threading.RLock()
        self._project: dict | None = None
        self._project_path: Path | None = None
        self._dirty = False

    @classmethod
    def instance(cls) -> "ProjectService":
        if _instance is None:
            raise RuntimeError("ProjectService not initialized")
        return _instance

    @property
    def project(self) -> dict | None:
        return self._project

    @property
    def media(self) -> dict:
        return self._project["media"] if self._project else {}

    @property
    def segments(self) -> list[dict]:
        return self._project["transcript"]["segments"] if self._project else []

    @property
    def edits(self) -> list[dict]:
        return self._project["edits"] if self._project else []

    def create(self, name: str, media_path: str) -> dict:
        """Create a new project from a media file."""
        from core.services.ffmpeg_service import probe_media

        # Probe media
        probe = probe_media(media_path)
        media_hash = self._compute_hash(media_path)

        self._project = {
            "schema_version": "1.0",
            "project": {
                "name": name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            "media": {
                "path": media_path,
                "media_hash": media_hash,
                "duration": probe.duration,
                "format": probe.format,
                "width": probe.width,
                "height": probe.height,
                "fps": probe.fps,
                "audio_channels": probe.audio_channels,
                "sample_rate": probe.sample_rate,
                "bit_rate": probe.bit_rate,
                "proxy_path": None,
                "waveform_path": None,
            },
            "transcript": {
                "engine": "manual_srt",
                "language": "zh",
                "segments": [],
            },
            "analysis": {
                "last_run": None,
                "silence_segments": [],
                "filler_hits": [],
                "error_patterns": [],
                "repetitions": [],
            },
            "edits": [],
            "export_history": [],
        }

        projects_dir = get_projects_dir()
        projects_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        self._project_path = projects_dir / f"{safe_name}.json"

        self._dirty = False
        self._auto_save()
        return self._project

    def open(self, project_path: str) -> dict:
        path = Path(project_path)
        if not path.exists():
            raise FileNotFoundError(f"Project file not found: {project_path}")

        content = path.read_text(encoding="utf-8")
        self._project = json.loads(content)
        self._project_path = path

        # Validate media file exists
        media_path = self._project["media"]["path"]
        if not Path(media_path).exists():
            logger.warning("Media file not found: {}", media_path)

        self._dirty = False
        return self._project

    def save(self) -> None:
        if self._project is None or self._project_path is None:
            return

        self._project["project"]["updated_at"] = datetime.now().isoformat()

        # Atomic write
        import tempfile
        fd, tmp_path = tempfile.mkstemp(
            dir=self._project_path.parent, suffix=".tmp", prefix="milo_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._project, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, str(self._project_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        self._dirty = False
        self._emit("project:saved", {"path": str(self._project_path)})
        logger.info("Project saved: {}", self._project_path)

    def _auto_save(self) -> None:
        """Save to autosave directory (non-blocking)."""
        if self._project is None:
            return
        # TODO: Implement autosave to autosave/ directory

    def close(self) -> None:
        if self._dirty:
            self.save()
        self._project = None
        self._project_path = None

    # ------------------------------------------------------------------
    # Subtitle operations
    # ------------------------------------------------------------------

    def import_srt(self, srt_path: str) -> list[dict]:
        """Import SRT file and populate transcript segments."""
        from core.services.subtitle_service import parse_srt_file, validate_srt

        content = Path(srt_path).read_text(encoding="utf-8-sig")
        duration = self._project["media"]["duration"]

        issues = validate_srt(content, duration)
        if issues:
            # Emit warnings but don't block
            for issue in issues:
                logger.warning("SRT validation: {}", issue)

        parsed = parse_srt_file(srt_path)
        segments = []
        for i, sub in enumerate(parsed):
            segments.append({
                "id": f"seg_{i+1:03d}",
                "version": 1,
                "type": "subtitle",
                "start": sub.start,
                "end": sub.end,
                "text": sub.text,
                "words": [],
                "speaker": None,
                "dirty_flags": {
                    "textChanged": False,
                    "timeChanged": False,
                    "analysisStale": False,
                },
            })

        self._project["transcript"]["segments"] = segments
        self._dirty = True
        self._auto_save()

        self._emit("project:dirty", {})
        return segments

    def update_segment_text(self, segment_id: str, text: str) -> None:
        for seg in self._project["transcript"]["segments"]:
            if seg["id"] == segment_id:
                seg["text"] = text
                seg["dirty_flags"]["textChanged"] = True
                seg["dirty_flags"]["analysisStale"] = True
                seg["version"] += 1
                self._dirty = True
                self._auto_save()
                return

    def merge_segments(self, segment_ids: list[str]) -> dict:
        """Merge multiple segments into one."""
        targets = [s for s in self._project["transcript"]["segments"]
                   if s["id"] in segment_ids]
        if not targets:
            raise ValueError("No matching segments found")

        targets.sort(key=lambda s: s["start"])
        merged = {
            "id": targets[0]["id"],
            "version": 1,
            "type": targets[0]["type"],
            "start": targets[0]["start"],
            "end": targets[-1]["end"],
            "text": " ".join(t["text"] for t in targets),
            "words": [],
            "speaker": targets[0]["speaker"],
            "dirty_flags": {
                "textChanged": True,
                "timeChanged": True,
                "analysisStale": True,
            },
        }

        # Remove old segments, add merged
        remaining = [s for s in self._project["transcript"]["segments"]
                    if s["id"] not in segment_ids]
        remaining.append(merged)

        self._project["transcript"]["segments"] = remaining
        self._dirty = True
        self._auto_save()
        return merged

    def split_segment(self, segment_id: str, position: float) -> list[dict]:
        """Split a segment at a given time position."""
        segments = self._project["transcript"]["segments"]
        for i, seg in enumerate(segments):
            if seg["id"] == segment_id:
                if position <= seg["start"] or position >= seg["end"]:
                    raise ValueError("Split position outside segment range")

                first_half = {**seg, "end": position}
                second_half = {
                    **seg,
                    "id": f"{seg['id']}_b",
                    "start": position,
                    "text": "",  # User will fill in
                }

                segments[i:i+1] = [first_half, second_half]
                self._dirty = True
                self._auto_save()
                return [first_half, second_half]

        raise ValueError(f"Segment {segment_id} not found")

    def search_replace(self, query: str, replacement: str, scope: str = "all") -> int:
        """Search and replace in segment texts. Returns count of replacements."""
        count = 0
        for seg in self._project["transcript"]["segments"]:
            if query in seg["text"]:
                seg["text"] = seg["text"].replace(query, replacement)
                seg["dirty_flags"]["textChanged"] = True
                seg["dirty_flags"]["analysisStale"] = True
                seg["version"] += 1
                count += 1

        if count > 0:
            self._dirty = True
            self._auto_save()
        return count

    # ------------------------------------------------------------------
    # Edit decisions
    # ------------------------------------------------------------------

    def mark_segments(self, segment_ids: list[str], action: str) -> None:
        """Mark segments for deletion/keep."""
        for edit in self._project["edits"]:
            if edit["id"] in segment_ids:
                edit["status"] = "confirmed" if action == "delete" else "rejected"
        self._dirty = True
        self._auto_save()

    def confirm_all_suggestions(self) -> int:
        count = 0
        for edit in self._project["edits"]:
            if edit["status"] == "pending" and edit["action"] == "delete":
                edit["status"] = "confirmed"
                count += 1
        if count > 0:
            self._dirty = True
            self._auto_save()
        return count

    def reject_all_suggestions(self) -> int:
        count = 0
        for edit in self._project["edits"]:
            if edit["status"] == "pending":
                edit["status"] = "rejected"
                count += 1
        if count > 0:
            self._dirty = True
            self._auto_save()
        return count

    def get_edit_summary(self) -> dict:
        """Compute export summary for the summary modal."""
        total_duration = self._project["media"]["duration"]
        confirmed_deletes = [e for e in self._project["edits"]
                             if e["action"] == "delete" and e["status"] == "confirmed"]
        deleted_duration = sum(e["end"] - e["start"] for e in confirmed_deletes)

        return {
            "total_duration": total_duration,
            "delete_count": len(confirmed_deletes),
            "deleted_duration": deleted_duration,
            "result_duration": total_duration - deleted_duration,
            "delete_ratio": deleted_duration / total_duration if total_duration > 0 else 0,
            "has_long_segment": any(e["end"] - e["start"] > 60 for e in confirmed_deletes),
        }

    def get_recent_projects(self) -> list[dict]:
        """List recently opened projects."""
        projects_dir = get_projects_dir()
        if not projects_dir.exists():
            return []

        projects = []
        for path in sorted(projects_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                projects.append({
                    "path": str(path),
                    "name": data.get("project", {}).get("name", path.stem),
                    "updated_at": data.get("project", {}).get("updated_at", ""),
                })
            except Exception:
                continue
        return projects[:10]

    @staticmethod
    def _compute_hash(file_path: str) -> str:
        """Compute SHA256 hash of first 10MB for integrity check."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(10 * 1024 * 1024), b""):
                if not chunk:
                    break
                sha.update(chunk)
        return f"sha256:{sha.hexdigest()[:32]}"
```

---

## 9. 日志配置（core/logging.py）

参考 ff-intelligent-neo 的 loguru 集成模式：

```python
# core/logging.py
"""Loguru logging configuration with optional frontend sink."""

from __future__ import annotations

import sys
from loguru import logger

# Remove default handler
logger.remove()

# Console sink
logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
)


def setup_frontend_sink(emit: "Callable") -> None:
    """Add a sink that forwards log messages to the frontend via bridge events."""
    def _frontend_sink(message: str) -> None:
        record = message.record
        emit("log_line", {
            "level": record["level"].name,
            "message": record["message"],
            "module": record["name"],
        })

    logger.add(_frontend_sink, level="INFO", format="{message}")


def get_logger():
    return logger
```

---

## 10. 路径配置（core/paths.py）

```python
# core/paths.py
"""Application data directory paths."""

from pathlib import Path
import sys

def get_base_dir() -> Path:
    """Platform-specific data directory."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "Milo-Cut"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Milo-Cut"
    else:
        base = Path.home() / ".config" / "milo-cut"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_projects_dir() -> Path:
    return get_base_dir() / "projects"


def get_cache_dir() -> Path:
    cache = get_base_dir() / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def get_autosave_dir() -> Path:
    autosave = get_base_dir() / "autosave"
    autosave.mkdir(parents=True, exist_ok=True)
    return autosave
```

---

## 11. FFmpeg 设置（core/ffmpeg_setup.py）

参考 ff-intelligent-neo 的 FFmpeg 发现和下载机制：

```python
# core/ffmpeg_setup.py
"""FFmpeg/ffprobe binary discovery and management."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_ffmpeg_path: str | None = None
_ffprobe_path: str | None = None


def get_ffmpeg_path() -> str | None:
    global _ffmpeg_path
    if _ffmpeg_path:
        return _ffmpeg_path
    _ffmpeg_path = shutil.which("ffmpeg")
    return _ffmpeg_path


def get_ffprobe_path() -> str | None:
    global _ffprobe_path
    if _ffprobe_path:
        return _ffprobe_path
    _ffprobe_path = shutil.which("ffprobe")
    return _ffprobe_path


def ensure_ffmpeg() -> bool:
    """Check if FFmpeg is available. Returns True if ready."""
    return get_ffmpeg_path() is not None and get_ffprobe_path() is not None


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)
```

---

## 12. 应用设置（core/config.py）

```python
# core/config.py
"""Application settings persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from core.paths import get_base_dir


@dataclass(frozen=True)
class MiloCutSettings:
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    theme: str = "auto"
    language: str = "zh-CN"
    silence_min_duration: float = 1.0
    silence_noise_tolerance: int = -30

    def to_dict(self) -> dict:
        return {
            "ffmpeg_path": self.ffmpeg_path,
            "ffprobe_path": self.ffprobe_path,
            "theme": self.theme,
            "language": self.language,
            "silence_min_duration": self.silence_min_duration,
            "silence_noise_tolerance": self.silence_noise_tolerance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MiloCutSettings":
        return cls(
            ffmpeg_path=data.get("ffmpeg_path", ""),
            ffprobe_path=data.get("ffprobe_path", ""),
            theme=data.get("theme", "auto"),
            language=data.get("language", "zh-CN"),
            silence_min_duration=data.get("silence_min_duration", 1.0),
            silence_noise_tolerance=data.get("silence_noise_tolerance", -30),
        )


_SETTINGS_PATH = get_base_dir() / "settings.json"


def load_settings() -> MiloCutSettings:
    if _SETTINGS_PATH.exists():
        try:
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
            return MiloCutSettings.from_dict(data)
        except Exception:
            pass
    return MiloCutSettings()


def save_settings(settings: MiloCutSettings) -> None:
    get_base_dir().mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(settings.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_app_info() -> dict:
    """Return application metadata and tool versions."""
    info = {"app_name": "Milo-Cut", "version": "0.1.0"}

    ffmpeg = get_ffmpeg_path()
    if ffmpeg:
        info["ffmpeg_path"] = ffmpeg
        try:
            result = subprocess.run(
                [ffmpeg, "-version"], capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if result.returncode == 0:
                first_line = result.stdout.split("\n")[0]
                info["ffmpeg_version"] = first_line
        except Exception:
            pass

    return info
```

---

## 13. 后端项目文件结构

```
core/
  __init__.py
  api.py                    -- (未使用，逻辑在 main.py 的 MiloCutApi 中)
  events.py                 -- 事件名常量
  models.py                 -- 数据模型 (MiloTask, Segment, EditDecision 等)
  task_manager.py           -- 统一任务管理器
  config.py                 -- 应用设置 (MiloCutSettings)
  paths.py                  -- 数据目录路径
  logging.py                -- loguru 配置 + 前端日志转发
  ffmpeg_setup.py           -- FFmpeg/ffprobe 发现
  services/
    __init__.py
    ffmpeg_service.py       -- FFmpeg/ffprobe 进程封装
    audio_service.py        -- 音频提取
    silence_service.py      -- 静音检测 (silencedetect)
    analysis_service.py    -- 多层分析编排
    subtitle_service.py     -- SRT 导入/解析/验证
    export_service.py       -- 多格式导出 (精确/快速)
    project_service.py      -- 项目 CRUD + JSON 持久化
    preview_service.py      -- 代理文件生成 (P1)
    vad_service.py          -- VAD 检测 (P1)
    asr_service.py          -- ASR 转写 (P1)
main.py                     -- 入口：MiloCutApi + App
pyproject.toml              -- uv 项目配置
```

---

## 14. 开发约定

### 代码风格
- 所有 `@expose` 方法返回 `dict`，格式 `{"success": bool, "data": ..., "error": ...}`
- frozen dataclass 用于配置/数据传输，可变 dataclass 仅用于运行状态
- 类型注解覆盖所有公共函数签名
- 使用 loguru 而非 print/stdout

### 线程安全
- `_emit()` 可从任意线程调用，事件队列自动序列化
- TaskManager 使用 `ThreadPoolExecutor` + `threading.Event` 管理后台任务
- ProjectService 使用 `RLock` 保护项目数据读写

### 错误处理
- `@expose` 装饰器自动捕获异常并返回安全错误消息
- 任务处理器抛出的异常被 TaskManager 捕获，转为 `failed` 状态
- FFmpeg 进程异常退出时清理临时文件

### 持久化
- 项目文件使用原子写入（temp file + `os.replace`）
- 设置文件使用简单 JSON 读写
- 崩溃恢复：autosave 目录保存最后有效状态

### 进程管理
- FFmpeg 进程使用 `CREATE_NO_WINDOW`（Windows）避免弹出控制台
- 取消信号通过 `threading.Event` 传递
- `on_closing` 回调确保窗口关闭时清理所有子进程
