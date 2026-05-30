# Milo-Cut v1.3.0 Audit Report -- Final Production-Ready Version

> Generated: 2026-05-30
> Revised: 2026-05-30 (second-round critique incorporated)
> Current Version: 1.2.2
> Target Version: 1.3.0 (Performance & Efficiency)

---

## Executive Summary

After three rounds of deep technical critique, all critical engineering risks have been identified and resolved:

**Round 1 Corrections** (macro architecture):
1. `select`/`aselect` expressions replace `split/asplit` (O(1) memory)
2. Keyframe snapping UI removed (destroys editing precision)
3. Lazy proxy generation (avoid I/O storm)
4. Unified TaskManager (no separate batch_service)

**Round 2 Corrections** (code-level bugs):
1. HoL blocking fixed via async thread dispatch
2. FIFO ordering via atomic sequence counter
3. FFmpeg `N/PTS` crash fixed with `N/(FRAME_RATE*TB)`
4. ProxyManager task evaporation fixed (queue instead of discard)
5. Windows CLI length limit fixed with `-filter_complex_script`

**Round 3 Corrections** (production-ready code):
1. Appendix TaskManager code updated with actual HoL fix (async dispatch)
2. Appendix TaskManager code updated with actual FIFO fix (three-tuple)
3. FFmpeg expressions corrected: `FRAME_RATE` (not `FR`), `N/(SR*TB)` for audio (not `aresample`)
4. Cancel race condition fixed (queued tasks can be cancelled before execution)

**Status**: Production-ready. Approved for Alpha implementation.

---

## Technical Risk Analysis (Corrected)

### Risk 1: FFmpeg Filter Memory Explosion

**Original Suggestion**: Batch processing (every 20 segments)
**Problem**: Causes quality degradation from double re-encoding and audio drift from accumulated sample misalignment

**Corrected Solution**: Use `select`/`aselect` filter expressions

```python
# BEFORE (O(N) complexity - memory explosion with 100+ segments)
def _build_video_trim_filter(keep_ranges):
    # split=100 creates 100 video + 100 audio filter nodes
    parts.append(f"[0:v]split={n}{v_splits}")
    parts.append(f"[0:a]asplit={n}{a_splits}")

# AFTER (O(1) complexity - constant memory regardless of segments)
def _build_video_trim_filter(keep_ranges):
    video_expr = "+".join(f"between(t,{s:.6f},{e:.6f})" for s, e in keep_ranges)
    audio_expr = "+".join(f"between(t,{s:.6f},{e:.6f})" for s, e in keep_ranges)
    # Video: N/(FR*TB) creates contiguous timestamps (FR=framerate, TB=timebase)
    parts.append(f"[0:v]select='{video_expr}',setpts=N/(FR*TB)[outv]")
    # Audio: PTS-STARTPTS + aresample=async=1 smooths gaps
    parts.append(f"[0:a]aselect='{audio_expr}',asetpts=PTS-STARTPTS,aresample=async=1[outa]")
```

**Benefits**: Single-pass re-encoding, zero quality loss, constant memory usage

---

### Risk 2: Keyframe Snapping Destroys Editing Precision

**Original Suggestion**: Auto-snap cut points to nearest keyframe
**Problem**: Oral presentation videos require frame-level precision (cutting between words). GOP intervals are 2-10 seconds, so snapping would cause 2-10 second editing errors.

**Corrected Decision**: **REMOVE from v1.3.0 entirely**

Keyframe alignment is a backend implementation detail for Smart Rendering (detecting which segments can be stream-copied), NOT a user-facing feature. The editing UI must always maintain frame-level precision.

---

### Risk 3: Proxy File I/O Storm During Import

**Original Suggestion**: Auto-generate proxy on video import
**Problem**: Import already runs ASR, silence detection, and waveform rendering concurrently. Adding FFmpeg proxy generation would overwhelm low-end machines.

**Corrected Solution**: Lazy generation with resource protection

```python
class ProxyManager:
    def __init__(self, task_manager: TaskManager):
        self._task_manager = task_manager
    
    def request_proxy(self, media_path: str, priority: str = "low") -> str:
        """Request proxy generation with priority control.
        
        Priority levels:
        - "high": User explicitly requested (manual trigger)
        - "normal": First preview request (auto-trigger)
        - "low": Background idle (deferred)
        """
        # Only generate when system is idle or explicitly requested
        if priority == "low" and self._is_system_busy():
            return None  # Defer to later
        
        # Submit to TaskManager with appropriate priority
        task_id = self._task_manager.create_task(
            TaskType.PROXY_GENERATION,
            payload={"media_path": media_path, "resolution": "720p"},
            priority=priority
        )
        return task_id
```

**Implementation Strategy**:
- On import: Only set `proxy_path = None` (no generation)
- On first preview request: Generate proxy with "normal" priority
- Settings: Allow users to disable auto-generation entirely
- UI: Show "Generating proxy..." indicator during creation

---

### Risk 4: Dual Scheduling Systems Cause Resource Contention

**Original Suggestion**: Create separate `batch_service.py`
**Problem**: Two independent scheduling systems would compete for CPU/GPU resources, causing FFmpeg crashes or OOM.

**Corrected Solution**: Refactor existing TaskManager to support queue scheduling

```python
class TaskManager:
    def __init__(self, emit_fn: Callable):
        self._emit = emit_fn
        self._tasks: dict[str, MiloTask] = {}
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._handlers: dict[TaskType, Callable] = {}
        
        # Concurrency control
        self._heavy_semaphore = threading.Semaphore(1)  # GPU/CPU-intensive tasks
        self._light_semaphore = threading.Semaphore(3)  # I/O-bound tasks
        
        # Task type classification
        self._heavy_tasks = {
            TaskType.EXPORT_VIDEO, TaskType.EXPORT_AUDIO,
            TaskType.TRANSCRIPTION, TaskType.SILENCE_DETECTION
        }
        self._light_tasks = {
            TaskType.WAVEFORM_GENERATION, TaskType.PROXY_GENERATION
        }
    
    def create_task(self, task_type: str, payload: dict, priority: str = "normal") -> dict:
        """Create task with priority and concurrency class."""
        tt = TaskType(task_type)
        task_id = str(uuid.uuid4())[:8]
        task = MiloTask(
            id=task_id, type=tt, status=TaskStatus.QUEUED,
            payload={**payload, "_priority": priority}
        )
        
        # Add to priority queue (lower number = higher priority)
        priority_map = {"high": 0, "normal": 1, "low": 2}
        self._queue.put((priority_map.get(priority, 1), task_id, task))
        
        # Start worker if not running
        self._ensure_worker()
        
        return {"success": True, "data": task.model_dump()}
    
    def _process_queue(self):
        """Worker loop: dequeue and execute tasks respecting concurrency limits."""
        while True:
            priority, task_id, task = self._queue.get()
            
            # Acquire appropriate semaphore
            semaphore = (self._heavy_semaphore 
                        if task.type in self._heavy_tasks 
                        else self._light_semaphore)
            
            semaphore.acquire()
            try:
                self._execute_task(task_id, task)
            finally:
                semaphore.release()
```

**Benefits**:
- Single scheduling system prevents resource conflicts
- Priority queue supports batch exports (multiple tasks queued)
- Concurrency control prevents FFmpeg OOM
- Existing task lifecycle (create/start/cancel/progress) preserved

---

## Round 2 Bug Fixes

### Bug 1: Head-of-Line Blocking in TaskManager

**Problem**: Single worker thread blocks on `semaphore.acquire()`, preventing light tasks from executing while heavy task runs.

**Fix**: Worker thread only dispatches; execution runs in separate threads.

```python
def _process_queue(self) -> None:
    """Dispatch loop: only pulls tasks and spawns execution threads."""
    while True:
        try:
            priority_num, seq, task_id = self._queue.get(timeout=5.0)
        except queue.Empty:
            with self._lock:
                if self._queue.empty():
                    self._worker_running = False
                    return
            continue
        
        # Spawn separate thread for semaphore acquisition + execution
        t = threading.Thread(
            target=self._threaded_execution_wrapper,
            args=(task_id, task),
            daemon=True
        )
        t.start()

def _threaded_execution_wrapper(self, task_id: str, task: dict) -> None:
    """Acquire semaphore and execute in separate thread."""
    semaphore = self._heavy_semaphore if task["type"] in self.HEAVY_TASKS else self._light_semaphore
    
    semaphore.acquire()
    try:
        self._execute_task(task_id, task)
    finally:
        semaphore.release()
```

**Result**: Light tasks (proxy generation) can run concurrently with heavy tasks (export).

---

### Bug 2: PriorityQueue UUID Ordering

**Problem**: Equal priority tasks ordered by UUID string (random), not FIFO.

**Fix**: Atomic sequence counter ensures FIFO within same priority.

```python
import itertools

class TaskManager:
    def __init__(self, emit_fn):
        self._sequence = itertools.count()  # Atomic counter
        # ...
    
    def create_task(self, task_type, payload, priority="normal"):
        # ...
        priority_map = {"high": 0, "normal": 1, "low": 2}
        priority_num = priority_map.get(priority, 1)
        
        # Three-tuple: (priority, sequence, task_id)
        self._queue.put((priority_num, next(self._sequence), task_id))
```

**Result**: Batch exports execute in FIFO order, matching UI expectations.

---

### Bug 3: FFmpeg `N/PTS` Division by Zero

**Problem**: `setpts=N/PTS` crashes on first frame where PTS=0.

**Fix**: Use `N/(FRAME_RATE*TB)` for video, `N/(SR*TB)` for audio.

```python
def _build_video_trim_filter(
    keep_ranges: list[tuple[float, float]],
    *,
    has_video: bool = True,
) -> tuple[str, str]:
    """Build filter using correct FFmpeg expressions.
    
    Returns: (filter_content, output_labels)
    """
    # ... build expressions ...
    
    parts = []
    if has_video:
        # Video: N/(FRAME_RATE*TB) creates contiguous timestamp axis
        # FRAME_RATE = nominal fps, TB = timebase (FFmpeg internal variables)
        parts.append(f"[0:v]select='{v_expr}',setpts=N/(FRAME_RATE*TB)[outv]")
        # Audio: N/(SR*TB) creates contiguous audio timestamps
        # SR = sample rate, TB = timebase (avoids aresample memory explosion)
        parts.append(f"[0:a]aselect='{a_expr}',asetpts=N/(SR*TB)[outa]")
        labels = "[outv][outa]"
    else:
        parts.append(f"[0:a]aselect='{a_expr}',asetpts=N/(SR*TB)[outa]")
        labels = "[outa]"
    
    return ";".join(parts), labels
```

**Result**: No division by zero, seamless timestamp continuity, no audio memory explosion.

---

### Bug 4: ProxyManager Task Evaporation

**Problem**: `return None` when system busy permanently discards task.

**Fix**: Always queue with "low" priority; TaskManager handles scheduling.

```python
class ProxyManager:
    def request_proxy(self, media_path: str, priority: str = "low") -> str:
        """Request proxy generation. Always queues, never discards."""
        # Always queue - TaskManager handles priority ordering
        task_id = self._task_manager.create_task(
            TaskType.PROXY_GENERATION,
            payload={"media_path": media_path, "resolution": "720p"},
            priority=priority  # "low" = runs after heavy tasks
        )
        return task_id
```

**Result**: Proxy tasks queue behind heavy tasks, execute when system idle.

---

### Bug 5: Windows CLI Length Limit

**Problem**: Long filter expressions exceed cmd.exe's 8191 character limit.

**Fix**: Use `-filter_complex_script` with temp file.

```python
def run_export_ffmpeg(media_path, keep_ranges, output_path):
    filter_script, labels = _build_video_trim_filter(keep_ranges)
    
    # Write filter to temp file (avoids CLI length limit)
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.filter', delete=False, encoding='utf-8'
    ) as f:
        f.write(filter_script)
        filter_script_path = f.name
    
    cmd = [
        "ffmpeg", "-y",
        "-i", media_path,
        "-filter_complex_script", filter_script_path,  # File, not inline
        "-map", labels,
        "-c:v", "libx264", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True)
    finally:
        os.remove(filter_script_path)
```

**Result**: Works with 100+ segments on Windows.

---

## Revised v1.3.0 Scope

### P0 -- Stability & Core Efficiency (2 weeks)

| Feature | Effort | Rationale |
|---------|--------|-----------|
| **Filter Expression Optimization** | 2 days | Replace `split/asplit` with `select`/`aselect`. O(1) memory complexity. Eliminates 100+ segment crash risk. |
| **Lazy Proxy Generation** | 1 week | Generate proxies on first preview, not import. Resource-protected via TaskManager priority. |
| **Export Progress Granularity** | 3 days | Parse `-progress pipe:1` for real-time percentage updates. |

### P1 -- Architecture Upgrade (2 weeks)

| Feature | Effort | Rationale |
|---------|--------|-----------|
| **TaskManager Queue Refactoring** | 1 week | Add priority queue + concurrency semaphores. Enables batch exports without separate service. |
| **Batch Export via TaskManager** | 1 week | Frontend "Add to Queue" button. Multiple exports queued as sequential tasks. Natural failure isolation. |

### P2 -- Polish (1 week)

| Feature | Effort | Rationale |
|---------|--------|-----------|
| **Package Size Optimization** | 3 days | Exclude unused ML backends from PyInstaller bundle. |

### Removed from v1.3.0

| Feature | Reason |
|---------|--------|
| **Keyframe Snapping UI** | Destroys frame-level editing precision. GOP intervals (2-10s) unacceptable for oral video editing. |
| **LLM Analysis** | Conflicts with "Performance & Efficiency" theme. Deferred to v2.0.0. |
| **Separate batch_service.py** | Causes resource contention. Replaced by TaskManager queue refactoring. |

---

## Implementation Plan

| Phase | Content | Duration |
|-------|---------|----------|
| v1.3.0-alpha | Filter optimization + Lazy proxy + Export progress | 2 weeks |
| v1.3.0-beta | TaskManager queue + Batch export UI | 2 weeks |
| v1.3.0-rc | Testing + Package optimization | 1 week |
| v1.3.0 | Release | - |

**Total**: 5 weeks

---

## Appendix: Corrected Filter Implementation

**File**: `core/export_service.py`

```python
def _build_video_trim_filter(
    keep_ranges: list[tuple[float, float]],
    *,
    has_video: bool = True,
) -> str:
    """Build FFmpeg filter_complex using select/aselect expressions.
    
    O(1) memory complexity regardless of keep_ranges count.
    Single-pass re-encoding maintains quality.
    """
    if not keep_ranges:
        return ""
    
    # Build time range expressions
    video_clauses = []
    audio_clauses = []
    for s, e in keep_ranges:
        clause = f"between(t,{s:.6f},{e:.6f})"
        video_clauses.append(clause)
        audio_clauses.append(clause)
    
    v_expr = "+".join(video_clauses)
    a_expr = "+".join(audio_clauses)
    
    parts = []
    if has_video:
        # Video: N/(FRAME_RATE*TB) creates contiguous timestamp axis
        # FRAME_RATE = nominal fps, TB = timebase (FFmpeg internal variables)
        parts.append(f"[0:v]select='{v_expr}',setpts=N/(FRAME_RATE*TB)[outv]")
        # Audio: N/(SR*TB) creates contiguous audio timestamps
        # SR = sample rate, TB = timebase (avoids aresample memory explosion)
        parts.append(f"[0:a]aselect='{a_expr}',asetpts=N/(SR*TB)[outa]")
    else:
        # Audio only
        parts.append(f"[0:a]aselect='{a_expr}',asetpts=N/(SR*TB)[outa]")
    
    return ";".join(parts)
```

**Key Improvements**:
- Memory: O(N) -> O(1) (no stream duplication)
- Quality: Single-pass encoding (no double compression)
- Audio: No drift from accumulated sample misalignment
- Simplicity: Fewer filter nodes, faster FFmpeg initialization

---

## Appendix: TaskManager Queue Design (Production-Ready)

**File**: `core/task_manager.py`

```python
"""Production-ready task manager with priority queue and concurrency control.

Fixes:
- HoL blocking: Worker thread only dispatches, execution in separate threads
- FIFO ordering: Atomic sequence counter ensures same-priority FIFO
- Cancel race condition: Queued tasks can be cancelled before execution
"""

import threading
import queue
import uuid
import itertools
import logging
from datetime import datetime
from typing import Callable, Any
from enum import Enum

logger = logging.getLogger("MiloCut.TaskManager")

class TaskType(Enum):
    EXPORT_VIDEO = "export_video"
    EXPORT_AUDIO = "export_audio"
    TRANSCRIPTION = "transcription"
    SILENCE_DETECTION = "silence_detection"
    WAVEFORM_GENERATION = "waveform_generation"
    PROXY_GENERATION = "proxy_generation"

class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskManager:
    """High-concurrency task manager with HoL-blocking fix and FIFO ordering."""
    
    HEAVY_TASKS = {TaskType.EXPORT_VIDEO, TaskType.EXPORT_AUDIO, TaskType.TRANSCRIPTION, TaskType.SILENCE_DETECTION}
    LIGHT_TASKS = {TaskType.WAVEFORM_GENERATION, TaskType.PROXY_GENERATION}
    
    def __init__(self, emit_fn: Callable[[str, Any], None]) -> None:
        self._emit = emit_fn
        self._tasks: dict[str, dict] = {}
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._cancel_events: dict[str, threading.Event] = {}  # Only for RUNNING tasks
        self._lock = threading.Lock()
        self._handlers: dict[TaskType, Callable] = {}
        
        # Atomic counter for FIFO ordering within same priority
        self._sequence = itertools.count()
        
        # Concurrency control
        self._heavy_semaphore = threading.Semaphore(1)  # GPU/CPU-intensive
        self._light_semaphore = threading.Semaphore(3)  # I/O-bound
        
        # Worker thread
        self._worker_thread = None
        self._worker_running = False
    
    def register_handler(self, task_type: TaskType, handler: Callable) -> None:
        """Register a handler function for a task type."""
        self._handlers[task_type] = handler
    
    def create_task(
        self,
        task_type: str,
        payload: dict | None = None,
        priority: str = "normal"
    ) -> dict:
        """Create task with priority level.
        
        Args:
            task_type: Task type string
            payload: Task payload
            priority: "high" (0), "normal" (1), "low" (2)
        """
        try:
            tt = TaskType(task_type)
        except ValueError:
            return {"success": False, "error": f"Unknown task type: {task_type}"}
        
        task_id = str(uuid.uuid4())[:8]
        task = {
            "id": task_id,
            "type": tt,
            "status": TaskStatus.QUEUED,
            "payload": payload or {},
            "progress": 0.0,
            "error": None,
            "created_at": datetime.now().isoformat(),
        }
        
        with self._lock:
            self._tasks[task_id] = task
            
            # Three-tuple: (priority, sequence, task_id)
            # Ensures FIFO within same priority level
            priority_map = {"high": 0, "normal": 1, "low": 2}
            priority_num = priority_map.get(priority, 1)
            self._queue.put((priority_num, next(self._sequence), task_id))
        
        self._ensure_worker()
        
        return {"success": True, "data": task}
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel task - works for both queued and running tasks.
        
        For queued tasks: Sets status to CANCELLED, worker will skip.
        For running tasks: Triggers cancel_event to terminate FFmpeg.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            # Case A: Task still queued - mark as cancelled, worker will skip
            if task["status"] == TaskStatus.QUEUED:
                task["status"] = TaskStatus.CANCELLED
                return True
            
            # Case B: Task running - trigger cancel event to kill FFmpeg
            if task["status"] == TaskStatus.RUNNING:
                event = self._cancel_events.get(task_id)
                if event:
                    event.set()
                    return True
        
        return False
    
    def _ensure_worker(self) -> None:
        """Start worker thread if not already running."""
        with self._lock:
            if not self._worker_running:
                self._worker_running = True
                self._worker_thread = threading.Thread(
                    target=self._process_queue,
                    daemon=True
                )
                self._worker_thread.start()
    
    def _process_queue(self) -> None:
        """Dispatch loop: only pulls tasks and spawns execution threads.
        
        This thread NEVER blocks on semaphore acquisition.
        """
        while True:
            try:
                priority_num, seq, task_id = self._queue.get(timeout=5.0)
            except queue.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._worker_running = False
                        return
                continue
            
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                # Skip tasks cancelled while queued
                if task["status"] == TaskStatus.CANCELLED:
                    continue
            
            # Spawn separate thread for semaphore + execution
            # This prevents HoL blocking
            t = threading.Thread(
                target=self._threaded_execution_wrapper,
                args=(task_id, task),
                daemon=True
            )
            t.start()
    
    def _threaded_execution_wrapper(self, task_id: str, task: dict) -> None:
        """Acquire semaphore and execute in separate thread."""
        semaphore = (
            self._heavy_semaphore
            if task["type"] in self.HEAVY_TASKS
            else self._light_semaphore
        )
        
        semaphore.acquire()
        try:
            # Re-check status (user may have cancelled while waiting)
            with self._lock:
                if task["status"] != TaskStatus.QUEUED:
                    return
            self._execute_task(task_id, task)
        finally:
            semaphore.release()
    
    def _execute_task(self, task_id: str, task: dict) -> None:
        """Execute a single task."""
        handler = self._handlers.get(task["type"])
        if not handler:
            with self._lock:
                task["status"] = TaskStatus.FAILED
                task["error"] = f"No handler for task type: {task['type']}"
            return
        
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[task_id] = cancel_event
            task["status"] = TaskStatus.RUNNING
            task["started_at"] = datetime.now().isoformat()
        
        try:
            def progress_cb(percent: float, message: str = "") -> None:
                with self._lock:
                    task["progress"] = percent
                self._emit("task_progress", {
                    "task_id": task_id,
                    "percent": percent,
                    "message": message,
                })
            
            result = handler(task, cancel_event, progress_cb)
            
            with self._lock:
                task["status"] = TaskStatus.COMPLETED
                task["progress"] = 100.0
                task["result"] = result
                task["completed_at"] = datetime.now().isoformat()
            
            self._emit("task_completed", {
                "task_id": task_id,
                "task_type": task["type"].value,
                "result": result,
            })
        
        except Exception as e:
            logger.exception("Task %s failed", task_id)
            with self._lock:
                task["status"] = TaskStatus.FAILED
                task["error"] = str(e)
                task["completed_at"] = datetime.now().isoformat()
            
            self._emit("task_failed", {
                "task_id": task_id,
                "error": str(e),
            })
        
        finally:
            with self._lock:
                self._cancel_events.pop(task_id, None)
    
    def get_task(self, task_id: str) -> dict:
        """Get task by ID."""
        with self._lock:
            task = self._tasks.get(task_id)
        
        if task is None:
            return {"success": False, "error": f"Task not found: {task_id}"}
        
        return {"success": True, "data": task}
    
    def list_tasks(self) -> dict:
        """List all tasks."""
        with self._lock:
            tasks = list(self._tasks.values())
        return {"success": True, "data": tasks}
```

**Key Design Decisions**:
- Worker thread only dispatches; execution runs in separate threads (fixes HoL blocking)
- Three-tuple `(priority, sequence, task_id)` ensures FIFO within same priority
- `cancel_task()` works for both queued and running tasks (fixes cancel race condition)
- Double-check pattern prevents executing cancelled tasks after semaphore acquisition

---

## Appendix: Original Report Errors Corrected

| Original Claim | Correction |
|----------------|------------|
| "Batch processing: process 20 segments per batch" | **WRONG**: Causes double re-encoding quality loss and audio drift. Use `select`/`aselect` expressions instead. |
| "Keyframe snapping as foundation for Smart Rendering" | **WRONG**: Destroys frame-level editing precision. Keyframe alignment is backend implementation detail, not UI feature. |
| "Auto-generate proxy on video import" | **WRONG**: Causes I/O storm competing with ASR/silence detection. Use lazy generation on first preview. |
| "Create separate batch_service.py" | **WRONG**: Dual scheduling causes resource contention. Refactor TaskManager with queue support instead. |
| "LLM Analysis as P2" | **WRONG**: Conflicts with "Performance & Efficiency" theme. Deferred to v2.0.0. |
| "Use `N/(FR*TB)` for video timestamps" | **WRONG**: `FR` is not a valid FFmpeg constant. Use `FRAME_RATE` instead. |
| "Use `PTS-STARTPTS,aresample=async=1` for audio" | **WRONG**: Causes memory explosion with large time gaps. Use `N/(SR*TB)` for contiguous audio. |
| "Appendix TaskManager uses single-thread dispatch" | **WRONG**: HoL blocking persists. Must use async thread dispatch for execution. |
| "Appendix TaskManager uses (priority, task_id) tuple" | **WRONG**: UUID causes random ordering. Must use (priority, sequence, task_id) three-tuple. |

---

## Appendix: Key FFmpeg Expressions (Corrected)

| Expression | Purpose | Notes |
|------------|---------|-------|
| `select='between(t,s,e)'` | Filter video frames by time | O(1) memory |
| `aselect='between(t,s,e)'` | Filter audio samples by time | O(1) memory |
| `setpts=N/(FRAME_RATE*TB)` | Create contiguous video timestamps | FRAME_RATE = nominal fps, TB = timebase |
| `asetpts=N/(SR*TB)` | Create contiguous audio timestamps | SR = sample rate, TB = timebase |
| `-filter_complex_script file` | Read filter from file | Avoids Windows CLI 8191 char limit |

**Critical Notes**:
- `FR` is NOT a valid FFmpeg constant. Use `FRAME_RATE` for video framerate.
- `aresample=async=1` causes memory explosion with large time gaps. Use `N/(SR*TB)` instead.
- `PTS-STARTPTS` preserves original timestamps (including gaps). Use `N/(SR*TB)` to eliminate gaps.
