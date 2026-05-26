# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- **Ignore**: `uv/`, `.venv/`, `*.bat`, `*_old/` directories.

## Prohibited Actions

- NEVER skip reading docs before coding
- NEVER modify code without understanding the corresponding business rule
- NEVER stop a task without code review and doc sync
- NEVER reuse context from a previous sub-agent task
- NEVER make more than one unverified change at a time
- NEVER ignore feedback from `feedback/index.md`

## Development Environment

- **OS**: Windows 11
- **Runtime**: Python 3.11+ / Node 20+
- **Package Manager (frontend)**: bun
- **Package Manager (backend)**: uv
- **Build Check (frontend)**: cd frontend && bun run build
