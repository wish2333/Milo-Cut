# v1.3.0 性能与效率 -- 实施记录

> **版本**: 1.3.0
> **主题**: 性能与效率
> **基准**: v1.2.2 (已发布)
> **分支**: `dev-1.3.0`
> **计划日期**: 2026-05-30
> **完成日期**: 2026-05-30
> **耗时**: 1小时2分52秒

---

## 概要

v1.3.0 为 Milo-Cut 的导出管线和任务管理带来三项重大改进：

1. **O(1) 内存导出** -- 用 `select`/`aselect` 滤镜表达式替换 `split/asplit` + `trim/atrim`，导出 100+ 片段不会内存爆炸。
2. **懒加载代理生成** -- 代理文件在首次预览请求时生成（而非导入时），避免与 ASR/静音检测竞争 I/O。
3. **批量导出** -- 通过 TaskManager 优先队列顺序导出多个项目，实时进度追踪。

---

## 提交记录

| 提交 | 说明 | 文件 |
|------|------|------|
| `b6b572b` | `perf(export): replace split/asplit with select/aselect for O(1) memory` | `core/export_service.py` |
| `c0db6a7` | `feat(export): add real-time progress parsing from FFmpeg -progress output` | `core/export_service.py` |
| `3e939cc` | `refactor(task): add priority queue with concurrency control and async dispatch` | `core/task_manager.py`, `core/proxy_manager.py`, `core/config.py`, `main.py` |
| `f7ebb1e` | `feat(batch): add batch export API, proxy UI, and package optimization` | `main.py`, `frontend/src/pages/WorkspacePage.vue`, `frontend/src/components/workspace/SettingsModal.vue`, `app.spec`, `build.py`, `frontend/vite.config.ts` |
| `0d99494` | `feat(batch): add batch export UI with project selector and progress` | `frontend/src/components/export/BatchExportPanel.vue`, `frontend/src/composables/useBatch.ts` |
| `ac4986d` | `chore(release): bump version to 1.3.0, fix proxy checkbox and defaults` | `pyproject.toml`, `frontend/package.json`, `app.spec`, `core/config.py`, `frontend/src/components/workspace/SettingsModal.vue`, `uv.lock`, `docs/1.3.0/` |

---

## 变更文件 (共 18 个)

### 后端 (7 个文件)

| 文件 | 变更 | 行数 |
|------|------|------|
| `core/export_service.py` | 用 `select`/`aselect` 替换 `split/asplit`；新增 `_parse_ffmpeg_progress()` 和 `_run_ffmpeg_with_progress()` | +101, -32 |
| `core/task_manager.py` | 重写为 `PriorityQueue` + `itertools.count()` FIFO，并发信号量，异步线程调度，`cancel_task()` | +191, -64 |
| `core/proxy_manager.py` | **新建** -- `ProxyManager` 类用于懒加载代理生成 | +115 |
| `core/ffmpeg_service.py` | 新增 `generate_proxy()` 函数 | +44 |
| `core/models.py` | `TaskType` 枚举新增 `PROXY_GENERATION = "proxy_generation"` | +1 |
| `core/config.py` | 新增 `proxy_resolution` 和 `proxy_auto_generate` 配置项 | +3 |
| `main.py` | 新增 `create_batch_export()`、`get_batch_status()`、代理处理器、`ProxyManager` 集成 | +193, -54 |

### 前端 (6 个文件)

| 文件 | 变更 | 行数 |
|------|------|------|
| `frontend/src/pages/WorkspacePage.vue` | 代理播放、"生成代理"按钮、加载指示器 | +58, -2 |
| `frontend/src/components/workspace/SettingsModal.vue` | 代理设置面板（分辨率下拉框、自动生成开关） | +29 |
| `frontend/src/components/export/BatchExportPanel.vue` | **新建** -- 批量导出 UI，含项目选择器和进度条 | +294 |
| `frontend/src/composables/useBatch.ts` | **新建** -- 批量状态管理组合式函数 | +168 |
| `frontend/src/types/edit.ts` | `AppSettings` 新增 `proxy_resolution` 和 `auto_generate_proxy` | +3 |
| `frontend/vite.config.ts` | 新增手动分块、压缩大小报告、chunkSizeWarningLimit | +13 |

### 构建 (2 个文件)

| 文件 | 变更 | 行数 |
|------|------|------|
| `app.spec` | 新增 `ML_EXCLUDES` 列表（40+ 重量级包） | +58 |
| `build.py` | 为 onefile 模式添加相同的 ML 排除项 | +17 |

---

## 逐任务详情

### 任务 1: 滤镜表达式优化

**目标**: 用 `select`/`aselect` 替换 `split/asplit` + `trim/atrim`，实现 O(1) 内存复杂度。

**优化前** (O(N) 内存):
```python
# split=100 创建 100 个视频 + 100 个音频滤镜节点
parts.append(f"[0:v]split={n}{v_splits}")
parts.append(f"[0:a]asplit={n}{a_splits}")
```

**优化后** (O(1) 内存):
```python
# 单个滤镜表达式，无流复制
parts.append(f"[0:v]select='{v_expr}',setpts=N/(FRAME_RATE*TB)[outv]")
parts.append(f"[0:a]aselect='{a_expr}',asetpts=N/(SR*TB)[outa]")
```

**关键常量**:
- `FRAME_RATE` -- 标称帧率（不是 `FR`，那是无效的）
- `SR` -- 采样率
- `TB` -- 时间基准

**验证**: 131 个测试通过，前端构建正常。

---

### 任务 2: PROXY_GENERATION 任务类型

**目标**: 将代理生成注册为 TaskManager 任务类型。

**变更**:
1. `core/models.py`: `TaskType` 枚举新增 `PROXY_GENERATION = "proxy_generation"`
2. `core/ffmpeg_service.py`: 新增 `generate_proxy()` 函数
3. `main.py`: 注册处理器 `_handle_proxy_generation`

**代理设置** (CRF 28, ultrafast 预设):
```python
cmd = [
    ffmpeg, "-y",
    "-i", media_path,
    "-vf", f"scale=-2:{height}",
    "-c:v", "libx264", "-crf", "28",
    "-preset", "ultrafast",
    "-c:a", "aac", "-b:a", "128k",
    "-movflags", "+faststart",
    output_path,
]
```

---

### 任务 3: 导出进度解析

**目标**: 解析 FFmpeg `-progress pipe:1` 输出，获取实时进度。

**实现**:
```python
def _parse_ffmpeg_progress(
    process: subprocess.Popen,
    total_duration_ms: float,
    progress_cb: Callable[[float, str], None] | None = None,
) -> None:
    for line in iter(process.stdout.readline, ""):
        if line.startswith("out_time_ms="):
            out_time_us = int(line.split("=", 1)[1])
            out_time_ms = out_time_us / 1000.0
            percent = min(100.0, (out_time_ms / total_duration_ms) * 100.0)
            if int(percent) != int(last_percent):
                progress_cb(percent, f"导出中... {percent:.1f}%")
```

**关键细节**: `out_time_ms` 单位是**微秒** -- 除以 1000 得到毫秒。

---

### 任务 4: TaskManager 队列重构

**目标**: 优先队列 + FIFO 排序 + 并发控制 + 异步调度。

**架构**:
```
create_task()
  -> PriorityQueue[(priority_num, sequence_counter, task_id)]
  -> _ensure_worker()

_process_queue()  [工作线程 -- 仅负责调度]
  -> _queue.get()
  -> 启动线程 -> _threaded_execution_wrapper()

_threaded_execution_wrapper()  [独立线程]
  -> semaphore.acquire()
  -> _execute_task()
  -> semaphore.release()
```

**并发策略**:
- 重任务（导出、转录）: `Semaphore(1)` -- 顺序执行
- 轻任务（波形、代理）: `Semaphore(3)` -- 并发执行

**FIFO 修复**: `itertools.count()` 确保同优先级任务按创建顺序执行。

**队头阻塞修复**: 工作线程仅负责调度，执行在独立线程中运行。

---

### 任务 5: 懒加载代理生成

**目标**: 在首次预览请求时生成代理（而非导入时）。

**ProxyManager**:
```python
class ProxyManager:
    def request_proxy(self, media_path: str, priority: str = "low") -> str:
        """始终入队，永不丢弃。"""
        task_id = self._task_manager.create_task(
            TaskType.PROXY_GENERATION,
            payload={"media_path": media_path, "resolution": "720p"},
            priority=priority
        )
        return task_id
```

**配置项** (`data/settings.json`):
- `proxy_resolution`: "720p"（默认）
- `proxy_auto_generate`: true（默认）

---

### 任务 6: 前端代理集成

**目标**: 使用代理播放，显示生成指示器，添加设置项。

**变更**:
1. `WorkspacePage.vue`: 更新 `loadVideoUrl()` 优先使用 `proxy_path`
2. `WorkspacePage.vue`: 新增"生成代理"按钮
3. `WorkspacePage.vue`: 新增"正在生成代理..."覆盖层
4. `SettingsModal.vue`: 新增代理分辨率下拉框 + 自动生成开关

---

### 任务 7: 批量导出后端

**目标**: 顺序导出多个项目。

**API**:
```python
@expose
def create_batch_export(self, project_paths: list[str]) -> dict:
    batch_id = uuid.uuid4().hex[:8]
    for path in project_paths:
        task = self._task_manager.create_task(
            TaskType.EXPORT_VIDEO,
            payload={"project_path": path, "batch_id": batch_id},
            priority="normal"
        )
    return {"batch_id": batch_id, "task_ids": task_ids, "total_count": len(project_paths)}
```

---

### 任务 8: 批量导出前端

**目标**: 项目选择 UI 和批量进度追踪。

**组件**:
- `BatchExportPanel.vue`: 项目选择器、导出设置、进度条
- `useBatch.ts`: 组合式函数，含 `createBatch()`、`pollBatchStatus()`、实时更新

---

### 任务 9: 打包体积优化

**目标**: 减小 PyInstaller 打包体积。

**变更**:
1. `app.spec`: 新增 `ML_EXCLUDES`（40+ 重量级包：torch、tensorflow、onnxruntime 等）
2. `build.py`: onefile 模式相同的排除项
3. `vite.config.ts`: Vue vendor 手动分块，压缩大小报告

**结果**: 为未来回归提供安全网（PyInstaller 本身已在正确排除）。

---

## 验证结果

### 最终验证波次

| 审查者 | 类别 | 结论 | 详情 |
|--------|------|------|------|
| F1: 计划合规审计 | `deep` | **通过** | 必须有 [5/5]，必须没有 [5/5] |
| F2: 代码质量审查 | `unspecified-high` | **通过** | 131 测试通过，vue-tsc + vite 构建正常 |
| F3: 手动 QA | `unspecified-high` | **通过** | 4/4 代码路径已验证 |
| F4: 范围保真检查 | `deep` | **通过** | 9/9 任务合规，无范围蔓延 |

### 测试结果

```
后端:  131 passed in 117.17s (0:01:57)
前端: vue-tsc --noEmit: PASS (0 type errors)
      vite build: PASS (built in 2.59s)
```

---

## 已知问题

1. **预存的 `aresample=async=1000`** 位于 `export_service.py` 第 770 行 -- 来自 v0.2.2 时代，非 v1.3.0 引入。数值不同（`1000` vs `1`），代码路径不同（concat 复用器，非滤镜表达式）。不阻塞。

2. **提交粒度**: 任务 2、5、6、7、9 合并为单个大型提交 `f7ebb1e`。流程偏差，非范围问题。

---

## 后续步骤

1. 从 `dev-1.3.0` 创建 PR 到 `main`
2. 使用 `uv run dev.py` 进行端到端测试
3. 准备 v1.3.0 发布说明

---

## Merge Message

```
feat: v1.3.0 Performance & Efficiency

- O(1) memory export: select/aselect replaces split/asplit
- Lazy proxy generation on first preview (not on import)
- Batch export with TaskManager priority queue
- Real-time export progress parsing
- Package size optimization (ML backend excludes)
```

---

## Release Note

### v1.3.0 -- 性能与效率

**导出管线优化**

- 滤镜表达式从 `split/asplit` 改为 `select`/`aselect`，内存复杂度从 O(N) 降至 O(1)，100+ 片段导出不再内存爆炸
- 使用 `-filter_complex_script` 临时文件，绕过 Windows 8191 字符限制
- FFmpeg 常量修正：`FRAME_RATE`（非 `FR`）、`N/(SR*TB)`（非 `aresample=async=1`）

**实时进度追踪**

- 解析 FFmpeg `-progress pipe:1` 输出，实时显示导出百分比
- 进度回调从 `subprocess.run` 升级为 `subprocess.Popen` + 实时行读取

**懒加载代理生成**

- 代理文件在首次预览时生成（非导入时），避免与 ASR/静音检测竞争 I/O
- `ProxyManager` 始终入队，永不丢弃
- 设置项：`proxy_resolution`（默认 720p）、`proxy_auto_generate`（默认关闭）

**TaskManager 重构**

- 优先队列 + `itertools.count()` 保证 FIFO 顺序
- 并发信号量：重任务（导出/转录）= 1，并发任务（波形/代理）= 3
- 异步线程调度解决队头阻塞问题
- `cancel_task()` 支持取消排队中和运行中的任务

**批量导出**

- `create_batch_export(project_paths)` 创建多个导出任务
- `get_batch_status(batch_id)` 查询批量进度
- 前端 `BatchExportPanel.vue` 提供项目选择器和进度条

**打包优化**

- PyInstaller 排除 40+ 重量级 ML 包（torch、tensorflow、onnxruntime 等）
- Vite 手动分块优化（Vue vendor 独立 chunk）

**UI 修复**

- 代理自动生成勾选框改用原版 HTML（DaisyUI 兼容问题）
- 代理自动生成默认关闭
