# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Milo-Cut is an AI-powered desktop video preprocessing tool for oral presentation videos. It's a Python (backend) + Vue 3 (frontend) hybrid application that runs inside a PyWebView window, communicating via a custom bridge layer (`pywebvue`).

## Development Commands

### Start the app (dev mode with Vite hot-reload)
```
uv run dev.py
```
This installs deps, starts Vite on :5173, then launches the PyWebView window.

### Start without Vite (uses pre-built frontend_dist/)
```
uv run dev.py --no-vite
```

### Install dependencies only
```
uv run dev.py --setup
```

### Frontend only (inside `frontend/`)
```
bun install          # install deps
bun run dev          # Vite dev server on :5173
bun run build        # type-check + build to ../frontend_dist/
bun run test         # vitest run
bun run test:watch   # vitest watch
```

### Backend tests
```
uv run pytest                              # all tests
uv run pytest tests/test_models.py         # single file
uv run pytest tests/test_models.py -k "test_name"  # single test
uv run pytest --cov=core --cov-report=term-missing  # with coverage
```

### Build distributable
```
uv run build.py              # onedir build
uv run build.py --onefile    # single executable
uv run build.py --clean      # remove build artifacts
```

## Architecture

### Backend-PyWebView-Frontend Bridge

The core communication pattern is:

1. **Python backend** (`core/`) implements services and data models
2. **`pywebvue/bridge.py`** provides `Bridge` base class with `@expose` decorator and event system
3. **`main.py:MiloCutApi`** subclasses `Bridge`, wires all `@expose`-decorated methods to frontend
4. **`pywebvue/app.py`** creates the PyWebView window, injects the bridge API as `window.pywebview.api`
5. **Frontend** calls `call("method_name", ...args)` via `src/bridge.ts`, receives typed `ApiResponse<T>`
6. **Events** flow Python -> JS via `Bridge._emit()` -> `CustomEvent("pywebvue:event_name")`, listened via `onEvent()` in `src/bridge.ts`

Key constraint: all `@expose` methods return `dict` with `{"success": bool, "data": ..., "error": ...}` envelope. The `@expose` decorator wraps exceptions automatically.

### Tick-based event loop

PyWebView only allows `evaluate_js` on the main thread. The bridge solves this with a tick pattern:
- A JS `setTimeout` loop calls `tick()` every 50ms
- `tick()` drains the event queue (Python -> JS events) and executes one queued task
- Background threads use `run_on_bridge(name, args)` to schedule work on the main thread

### Task system for long-running operations

Long operations (silence detection, export, analysis, waveform generation) go through `TaskManager`:
1. Frontend calls `create_task(task_type, payload)` -> gets a task ID
2. Frontend calls `start_task(task_id)` -> backend spawns a thread
3. Progress updates via `task:progress` events
4. Completion via `task:completed` / `task:failed` events

Task types are defined in `core/models.py:TaskType`.

### Backend Services (core/)

| Service | Responsibility |
|---------|---------------|
| `project_service.py` | Project CRUD, segment editing, analysis storage, edit decisions. Persists to `data/projects/<name>/project.json` |
| `export_service.py` | Video/audio/SRT export via FFmpeg segment-concat pipeline |
| `export_timeline.py` | OTIO/EDL/FCPXML/Premiere XML timeline export |
| `ffmpeg_service.py` | ffprobe/ffmpeg wrappers: media probing, silence detection, waveform generation |
| `analysis_service.py` | Rule-based Chinese filler word and error trigger detection |
| `subtitle_service.py` | SRT parsing with multi-encoding (UTF-8, GB18030, BOM) |
| `task_manager.py` | Background task execution with progress + cancellation |
| `media_server.py` | Local HTTP server for streaming video to `<video>` element |
| `models.py` | Pydantic v2 frozen models: Project, Segment, EditDecision, MediaInfo, MiloTask |

### Data model

All models use Pydantic v2 (`core/models.py`):
- `Project` -> `ProjectMeta`, `MediaInfo`, `TranscriptData` (contains `Segment[]`), `AnalysisData`, `EditDecision[]`
- `Segment` has `type` field: `subtitle | silence | gap`
- `EditDecision` tracks edit actions (delete, keep, trim) with statuses (pending, confirmed, rejected)

### Frontend architecture

Vue 3 + TypeScript + Vite + Tailwind CSS 4 + DaisyUI 5. No Vue Router -- uses conditional rendering in `App.vue` driven by reactive state:
- `WelcomePage` -> project creation/import
- `WorkspacePage` -> main editing workspace
- `ExportPage` -> export with encoding settings and preview

Composables in `src/composables/` follow the `use*` pattern and use `useBridge()` for lifecycle-managed event listeners. Components are organized by feature area (`common/`, `workspace/`, `export/`, `waveform/`).

### Event name contract

Event names in `core/events.py` must stay in sync with `frontend/src/utils/events.ts`. When adding new events, update both files.

### Media serving

`MediaServer` (`core/media_server.py`) starts a local HTTP server to stream media files to the HTML5 `<video>` element, since PyWebView cannot load `file://` URLs directly in all configurations.

## Key Conventions

- **API envelope**: Every `@expose` method returns `{"success": bool, "data": ..., "error": ...}`. Never return raw values.
- **`@` alias**: Frontend imports use `@/` for `src/`.
- **No emoji in code**: Terminal rendering issues on Windows -- avoid emoji in source code and commit messages.
- **Use `uv run`** for all Python execution, never bare `python`.
- **Use `bun`** as the primary frontend package manager (falls back to npm).
- **Python version**: 3.11 (pinned in `.python-version`)
- **Models**: Pydantic v2 with `frozen=True` for all data models
- **Settings**: Runtime config stored in `data/settings.json` (FFmpeg paths, silence thresholds, filler words, export codecs)
- **Project persistence**: Each project saves to `data/projects/<name>/project.json`
- **Ignore**: `uv/`, `.venv/`, `*.bat`, `*_old/` directories.

## Git Commit Style

两段式格式：主题行 + 空行 + 详细列表。

- **主题行**: `type(module): 简短摘要`，module 填修改的大致模块（如 export、project、workspace、ffmpeg），不用版本号
- **详细列表**: 空行后用 `- ` 开头逐条列出改动

```
feat(export): 视频编码参数系统完善 -- 编码器注册表、质量参数动态适配、像素格式探测

- 新建 core/ffmpeg_presets.py 编码器配置单一事实来源
- 修复硬件编码器 (-cq/-qp) 质量参数误用 (-crf) 问题
- 添加像素格式探测，HDR/10-bit 输入保留原始格式
```

## External Dependencies

- **FFmpeg/FFprobe**: Required at runtime, invoked as subprocesses. Paths configurable in `data/settings.json`.
- **pywebview**: Creates the native desktop window and hosts the Vue SPA.

## Development Environment

- **OS**: Windows 11
- **Package Manager (backend)**: uv
- **Package Manager (frontend)**: bun
- **Build Check (frontend)**: `cd frontend && bun run build`

## Documentation

Design specs and audit reports live in `docs/`. Key files:
- `docs/design-spec.md` - Apple Edition design language
- `docs/component-spec.md` - Component layout and interaction spec
- `docs/backend-guide.md` / `docs/frontend-guide.md` - Developer guides
- `tests/TEST_GUIDE.md` - Automated + manual test procedures
