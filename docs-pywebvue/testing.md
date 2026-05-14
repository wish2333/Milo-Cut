# PyWebVue Testing Guide

## Quick Start

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=pywebvue --cov-report=term-missing

# Run a single test module
uv run pytest tests/test_expose.py -v

# Run a single test by name
uv run pytest tests/test_event.py::TestEmitValidation::test_valid_event_names -v
```

## Test Structure

```
tests/
  __init__.py
  test_expose.py        -- @expose decorator: success, error modes (debug/prod)
  test_event.py         -- _emit() validation, _flush_events() serialization
  test_task_queue.py    -- run_on_bridge(), timeout, deprecated alias, concurrency
  test_dropped_files.py -- file drop parsing, buffer clearing, thread safety
```

## Coverage Scope

| Module | Coverage | Notes |
|--------|----------|-------|
| `bridge.py` | ~96% | Core logic fully covered |
| `__init__.py` | 100% | Re-exports only |
| `app.py` | ~29% | Requires pywebview window (integration test territory) |

`app.py` 的低覆盖率是预期行为 -- 它的核心功能是创建 pywebview 窗口和注入 JS，需要真实的 WebView2/WebKit 环境。这类测试属于集成测试范畴，需要手动验证或 E2E 框架。

## Writing New Tests

### 测试 Bridge 方法

`Bridge` 的所有核心逻辑都可以直接实例化后测试，无需 mock pywebview：

```python
from pywebvue.bridge import Bridge, expose


class MyBridge(Bridge):
    @expose
    def my_method(self, x: int) -> dict:
        return {"success": True, "data": x * 2}


def test_my_method():
    b = MyBridge()
    result = b.my_method(3)
    assert result == {"success": True, "data": 6}
```

### 测试事件推送

使用 `_FakeWindow` mock 来捕获 `evaluate_js` 调用：

```python
from tests.test_event import _FakeWindow


def test_my_event():
    b = Bridge()
    b._window = _FakeWindow(capture_js=True)
    b._emit("my-event", {"key": "value"})
    b._flush_events()
    js = b._window.captured_js[0]
    assert '"pywebvue:my-event"' in js
```

### 测试任务队列

任务队列依赖 tick 循环驱动。使用 `_start_tick_loop` 辅助函数模拟：

```python
import threading
from tests.test_task_queue import _start_tick_loop


def test_my_task():
    b = Bridge()
    b.register_handler("work", lambda args: args + 1)

    stop = threading.Event()
    tick = _start_tick_loop(b, stop)
    try:
        result = b.run_on_bridge("work", 41, timeout=2)
        assert result == 42
    finally:
        stop.set()
        tick.join(timeout=2)
```

### 测试模式总结

| 场景 | 方法 | 需要 mock? |
|------|------|-----------|
| `@expose` 方法返回值 | 直接调用实例方法 | 否 |
| 事件名校验 | 调用 `_emit()` | 否 |
| 事件序列化到 JS | `_FakeWindow` 捕获 JS | `_FakeWindow` |
| 任务队列执行 | `_start_tick_loop` 辅助 | 否 |
| 拖拽文件 | 直接调用 `_on_drop()` | 否 |

## Key Testing Principles

1. **不 mock pywebview** -- Bridge 的设计使得所有核心逻辑（事件队列、任务调度、drop 缓存）都可以脱离 pywebview 独立测试。只有 `_flush_events` 中的 `evaluate_js` 需要 mock window 对象。

2. **线程安全测试** -- 涉及队列和锁的组件都有并发测试（`test_dropped_files.py::TestDroppedFilesThreadSafety`、`test_task_queue.py::TestConcurrentTasks`）。新增线程相关的功能时应照此模式补充。

3. **tick 循环是外部依赖** -- 在生产环境中由 JS timer 驱动，测试中需要手动模拟。`_start_tick_loop` 提供了最简模拟。

## CI Integration

在 CI 管道中运行：

```bash
uv run pytest tests/ --cov=pywebvue --cov-fail-under=75
```

`--cov-fail-under=75` 确保覆盖率不低于当前基线。`app.py` 的窗口依赖逻辑会拉低整体覆盖率，因此阈值设为 75% 而非 80%。
