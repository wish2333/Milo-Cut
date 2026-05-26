# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Milo-Cut is an AI-powered video preprocessing tool for oral presentation videos. It detects silence, identifies filler words, and exports edited cuts. Built as a desktop app: Python backend + Vue 3 SPA frontend, bridged via pywebview.

## Development Commands

### Run in Development Mode
```bash
# One-click launcher (installs deps, starts Vite dev server + pywebview)
dev.bat          # Windows
./dev.sh         # macOS/Linux

# Or manually:
uv run python main.py
```

### Build for Distribution
```bash
uv run build.py              # PyInstaller onedir build
uv run build.py --onefile    # Single executable
uv run build.py --clean      # Clean build artifacts first
```

### Testing
```bash
# Backend (pytest, 64 tests)
uv run pytest tests/ -v
uv run pytest tests/ --cov=core --cov-report=term-missing

# Frontend (vitest, 23 tests)
cd frontend && bun run test
cd frontend && bun run test:coverage

# Single test file
uv run pytest tests/test_models.py -v
cd frontend && bun run test -- src/composables/useSegmentEdit.test.ts
```

### Frontend Only
```bash
cd frontend
bun install        # Install deps
bun run dev        # Vite dev server on port 5173
bun run build      # Production build to ../frontend_dist/
bun run test       # Run vitest
```

## Architecture

### Communication Bridge (pywebvue/)

The Python<->JS bridge is the central architectural pattern:

- **Python side**: `Bridge` base class with `@expose` decorator marks methods callable from JS. `_emit(event_name, data)` pushes events to the frontend as `CustomEvent("pywebvue:<name>")`.
- **JS side**: `bridge.ts` provides `call<T>(method, ...args)` to invoke Python methods, and `onEvent<T>(name, handler)` to listen for Python-pushed events.
- All API methods live in `main.py` class `MiloCutApi(Bridge)` (~30 exposed methods).

### Backend Services (core/)

| Service | Responsibility |
|---------|---------------|
| `project_service.py` | Project CRUD, segment editing, analysis storage, edit decisions. Persists to `data/projects/<name>/project.json` |
| `export_service.py` | Video/audio/SRT export via FFmpeg segment-concat pipeline |
| `ffmpeg_service.py` | ffprobe/ffmpeg wrappers: media probing, silence detection, waveform generation |
| `analysis_service.py` | Rule-based Chinese filler word and error trigger detection |
| `subtitle_service.py` | SRT parsing with multi-encoding (UTF-8, GB18030, BOM) |
| `task_manager.py` | Background task execution with progress + cancellation |
| `media_server.py` | Local HTTP server for streaming video to `<video>` element |
| `models.py` | Pydantic v2 frozen models: Project, Segment, EditDecision, MediaInfo, MiloTask |

### Frontend (frontend/src/)

- **Two pages**: `WelcomePage` (import/open) and `WorkspacePage` (main editor)
- **Composables** encapsulate state + bridge calls: `useProject`, `useEdit`, `useExport`, `useAnalysis`, `useTask`, `useSegmentEdit`, `useTimelineMetrics`, `useToast`, `useTranscript`
- **Waveform editor**: Canvas-based (`WaveformCanvas`, `WaveformEditor`, `PlayheadOverlay`, `ScrollbarStrip`, `SegmentBlocksLayer`, `TimeMarksLayer`)
- **UI**: TailwindCSS v4 + DaisyUI v5

### Data Flow

1. Frontend calls `bridge.call("method_name", ...args)` -> invokes Python `@expose` method
2. Python processes, optionally `_emit("event_name", data)` back to frontend
3. Frontend listens via `onEvent("event_name", handler)` and updates reactive state
4. FFmpeg operations run as background tasks via `TaskManager`, reporting progress through events

## Key Conventions

- **Python package manager**: UV (not pip). Always use `uv run` to execute Python scripts.
- **Node package manager**: Bun (not npm/yarn). Use `bun` in the frontend/ directory.
- **Python version**: 3.11 (pinned in `.python-version`)
- **Models**: Pydantic v2 with `frozen=True` for all data models
- **Event names**: Defined as constants in `core/events.py` (backend) and `frontend/src/utils/events.ts` (frontend)
- **Settings**: Runtime config stored in `data/settings.json` (FFmpeg paths, silence thresholds, filler words, export codecs)
- **Project persistence**: Each project saves to `data/projects/<name>/project.json`

## External Dependencies

- **FFmpeg/FFprobe**: Required at runtime, invoked as subprocesses. Paths configurable in `data/settings.json`.
- **pywebview**: Creates the native desktop window and hosts the Vue SPA.

## Documentation

Design specs and audit reports live in `docs/`. Key files:
- `docs/design-spec.md` - Apple Edition design language
- `docs/component-spec.md` - Component layout and interaction spec
- `docs/backend-guide.md` / `docs/frontend-guide.md` - Developer guides
- `tests/TEST_GUIDE.md` - Automated + manual test procedures
