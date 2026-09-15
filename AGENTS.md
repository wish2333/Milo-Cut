# AGENTS.md

This file provides guidance to coding agents (Codex / Claude Code / OpenCode / etc.) when working with code in this repository. It is the single source of agent-facing truth -- keep it in sync when architecture changes.

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
| `project_service.py` | Project CRUD, segment/edit/analysis/track ops, `_revision` counter, `_enforce_segment_sort_invariant`. Persists to `data/projects/<name>/project.json` |
| `project_patch.py` | v2.3.2 `ProjectPatch` schema + `apply_project_patch` + `is_stale_patch` |
| `persistence.py` | Crash-safe atomic saves (fsync + `.bak.1/.bak.2` rotation), corrupted-project auto-recovery |
| `migrations.py` | Schema migrations for legacy project files (word data, tracks, edit ranges) |
| `correction_service.py` | Subtitle correction pipeline: batching, cancel polling (`wait(FIRST_COMPLETED)`), track-scoped application, aligned-context re-translation of word timings |
| `export_service.py` | Video/audio/SRT/VTT export via FFmpeg segment-concat pipeline; highlight virtual edits; per-track + bilingual merged export |
| `export_timeline.py` | OTIO/EDL/FCPXML/Premiere XML timeline export (audio-only fps=0 safe since v2.3.1) |
| `ffmpeg_service.py` | ffprobe/ffmpeg wrappers: media probing, silence detection, waveform generation, peak cache, proxy generation |
| `ffmpeg_presets.py` | Encoder registry: CRF/CQ/QP selection, pixel format probing, hardware-acceleration mapping |
| `llm_service.py` | LLM provider abstraction (OpenAI-compatible: DeepSeek / OpenAI / Qwen / GLM / Ollama / custom) + smart-delete / correction / translation pipelines (batch ledger, incremental resume, quality mode sliding window) |
| `llm_prompts.py` | System prompts with template variable injection; partial_delete hint plumbing (v2.2.0); aligned_main_text context (v3.0.5) |
| `llm_presets.py` | Style presets for LLM prompts |
| `workflow_engine.py` | Multi-step workflow orchestration (silence detection + smart delete + subtitle correction) with per-step layer snapshots |
| `analysis_service.py` | Rule-based Chinese filler word and error-trigger detection |
| `subtitle_service.py` | SRT parsing with multi-encoding (UTF-8, GB18030, BOM) |
| `timeline_utils.py` | Timeline helpers, partial_delete hint collection |
| `diff_service.py` | Subtitle correction diff generation |
| `task_manager.py` | Background task execution with progress + cancellation |
| `track_constraints.py` | Stacked-timeline constraint kernel (overlap/linkage/reconcile; TS twin in `frontend/src/utils/trackConstraints.ts`) |
| `bridge_service.py` | HTTP bridge API (health, analyze endpoints) |
| `media_server.py` | Local HTTP server for streaming video to `<video>` element |
| `asr_service.py` | ASR plugin abstraction (faster-whisper, qwen3-asr) |
| `plugin_manager.py` | ASR plugin install / model download lifecycle |
| `proxy_manager.py` | Proxy video generation for large source files |
| `config.py` | Settings storage (`data/settings.json`), incl. `llm_translation_quality_mode` (v3.0.5) |
| `paths.py` | Cross-platform path resolution |
| `events.py` | Event name constants (must mirror `frontend/src/utils/events.ts`) |
| `models.py` | Pydantic v2 frozen models: Project, Timeline, Segment, Word, SubtitleTrack, TrackBinding, EditDecision, MediaInfo, AnalysisData, ProjectPatch, MiloTask |
| `logging.py` | Loguru setup |

### Data model

All models use Pydantic v2 (`core/models.py`) with `frozen=True`:

- `Project` → `ProjectMeta`, `MediaInfo | None`, `timelines: list[Timeline]`, `active_timeline_id`
- `Timeline` → `TranscriptData` (contains `Segment[]`), `edits: list[EditDecision]`, `AnalysisData`, `llm_prompts`
- `Segment.type` is `subtitle | silence` (no `gap` -- media gaps are inferred from non-overlapping segment times); `Segment.words` carries word-level timestamps (`Word` with `start`/`end`/`confidence`, v3.0.0)
- `TranscriptData.tracks: list[SubtitleTrack]` -- extension tracks (`role`: `extension | translation | caption`), each with its own `Segment[]`; `TrackBinding` binds extension segments 1:1 to main-track segments (`start_offset`/`end_offset` rebuilt wholesale from final geometry after every edit)
- `EditDecision` tracks edit actions (`delete` / `keep`) with statuses (`pending` / `confirmed` / `rejected`) and `target_type` (`segment` / `range`)
- `ProjectPatch` (v2.3.2) carries layer-scoped updates: `revision`, `segments?`, `edits?`, `analysis?`, `media?`, `active_timeline_id?`, `full_project?`

### v3.0.0 persistence & migrations

`core/persistence.py` writes project files atomically (temp file + fsync + rename) with rotating `.bak.1/.bak.2` backups; corrupted projects auto-recover from backups with a toast and self-heal on disk. `core/migrations.py` upgrades legacy project JSON (word data, tracks, edit ranges) on load -- never edit the on-disk schema without adding a migration.

### v3.0.4/v3.0.5 translation & correction pipelines

`llm_service.py` runs LLM translation in batches with a per-batch ledger (never silently drops a batch); partial failures land completed batches and surface the gap for one-click incremental resume (`start_translation` auto-routes to resume). Quality mode (`llm_translation_quality_mode`, default off) forces serial dispatch where batch N carries batch N-1's finalized translations. `correction_service.py` applies corrections track-scoped (`track_id`: `None` = legacy whole-timeline, `""` = main track, non-empty = extension track) and polls futures with `wait(1.0, FIRST_COMPLETED)` so cancellation returns in ~1s.

### Layered undo (v3.0.0)

Undo/redo goes through the backend `apply_undo` channel with per-layer snapshots (text / time / delete layers captured by predicate); undo on a 1167-segment project costs ~1.2 ms on the main thread with a strictly increasing revision. The frontend `useUndoRedo` composable owns the snapshot stack; `popSnapshot()` supports rollback-without-restore for idempotent duplicate operations (v3.0.5 R5.0).

### v2.3.2 ProjectPatch protocol

Migrated write methods (`update_edit_decision`, `update_edit_decisions_batch`, `mark_segments`, `update_segment`, `update_segment_text`) return a `ProjectPatch` envelope (`{success, data: ProjectPatch.model_dump(mode="json")}`) instead of the legacy full-Project dump. Other write methods keep the legacy `{success, data: project.model_dump()}` shape; the frontend auto-detects via the `revision` field.

Frontend entry point: `App.vue:onProjectUpdated` -- applies patch via `applyProjectPatch`, rejects stale patches via `lastSeenRevision`. Undo/redo snapshots are still full Project (pushSnapshot before applying the patch).

Reference: `core/project_patch.py`, `frontend/src/utils/projectPatch.ts`.

### v2.3.2 Sort invariant

`ProjectService._enforce_segment_sort_invariant()` guarantees `transcript.segments` is sorted by `start` ascending after any write that could disturb ordering (`update_transcript` always; `update_segment` when `start` changes). `add_segment` / `split_segment` / `merge_segments` preserve order naturally. The frontend `WorkspacePage.mergedSegments` computed relies on this and skips its per-render O(S log S) sort.

Regression coverage: `tests/test_segment_sort_invariant.py` (13 tests).

### v2.2.1 Bridge ready signal

`pywebvue/app.py:on_loaded` sets `window.__BRIDGE_READY__ = true` before the tick loop starts draining the queue. The frontend `bridge.ts:waitForPyWebView` waits for **both** `window.pywebview.api` and `window.__BRIDGE_READY__` -- checking only the former races against the pywebview `loaded` event and silently drops calls on macOS first launch (pywebview issue #431).

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

- **OS**: Cross-platform (developed on Windows 11 + macOS 26); `dev.py` / `build.py` work on both
- **Package Manager (backend)**: uv
- **Package Manager (frontend)**: bun
- **Build Check (frontend)**: `cd frontend && bun run build` (runs `vue-tsc --noEmit` + `vite build`)
- **Python version**: 3.11 (pinned in `.python-version`)
- **Models**: Pydantic v2 with `frozen=True` for all data models
- **Settings**: Runtime config stored in `data/settings.json` (FFmpeg paths, silence thresholds, filler words, export codecs, LLM provider)
- **Project persistence**: Each project saves to `data/projects/<name>/project.json`

## Documentation

Design specs, audit reports, and per-version implementation records live in `docs/`. Key entry points:
- `docs/design-spec.md` - Apple Edition design language
- `docs/backend-guide.md` / `docs/frontend-guide.md` - Early-stage developer guides (v0.x-era; this file is the authoritative current architecture reference)
- `docs/<version>/` - Per-version implementation records (`record-<v>.md`, audit reports, specs). Current: v0.1.0 through v3.0.5.
- `docs/3.0.5/record-3.0.5.md` - Latest release (v3.0.5 translation reliability + track-scoped correction)
- `tests/TEST_GUIDE.md` - Automated + manual test procedures
- `tests/perf/README.md` - Backend performance baseline harness
- `README.md` / `README_zh.md` - User-facing project overview (English / Chinese)
- `docs/agents/` - Agent-skill configuration (issue tracker, triage labels, domain docs)

## Agent skills

Matt Pocock's skills (installed under `.agents/skills/`) are configured as follows:

### Issue tracker

Local markdown: issues and specs live as files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five canonical roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` at the repo root plus `docs/adr/` for short ADRs, both created lazily by `/domain-modeling`. See `docs/agents/domain.md`.

Workflow entry points: daily router is `/ask-matt`; the working loop is `/grill-with-docs` (align before code) -> `/implement` (build to the agreed contract, driving `/tdd`). `/to-spec` and `/to-tickets` only for work that spans sessions or won't fit in one slice.
