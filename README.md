# Milo-Cut

> Turn 1 hour of raw footage into 40 minutes of clean, editable material. Edit video like editing a document -- with AI assistance.

Milo-Cut is a local-first, AI-powered desktop video preprocessing tool for oral presentation videos. It detects silence, analyzes content with LLM for smart trimming, corrects ASR transcription errors, and extracts highlights -- then lets you review and export clean footage. No cloud upload required.

## Features

### AI Assistance (LLM-powered)

- **AI Smart Delete** -- LLM analyzes transcript to flag filler words, repeated segments, self-corrections, and off-topic asides for bulk removal. Results are categorized (full delete vs partial delete) and feed back into subtitle correction as context hints (v2.2.0).
- **AI Subtitle Correction** -- LLM batch-corrects ASR recognition errors with side-by-side diff review. Accept high-confidence suggestions in one click or review each correction individually.
- **AI Highlight Extraction** -- LLM identifies key moments from long recordings; manually add or remove highlight segments via right-click. Highlights export to MP4 / audio / SRT via the "invert + delete" pipeline (v2.2.0).
- **AI Semantic Search** -- Natural-language queries to locate specific segments ("find the slide about Q3 revenue").
- **Prompt Presets & Editing** -- Customize LLM system prompts with style presets and template variable injection.

### Editing & Detection

- **Silence Detection** -- FFmpeg-powered with configurable threshold and duration; respects existing user / LLM decisions and never overwrites prior analysis results (v2.3.0 regression fix).
- **Filler Word Detection** -- Customizable word lists with regex matching for high-frequency filler words (Chinese-aware).
- **Error-Trigger Detection** -- Recognizes self-correction triggers like "不对重来" / "说错了" / "重新说".
- **Multi-Timeline Editing** -- Fork independent timelines from the current state; each timeline owns its own transcript, edits, and analysis. Switch between alternative cuts without losing prior work.
- **Workflow Engine** -- Orchestrate silence detection, smart delete, and subtitle correction in a configurable pipeline.
- **Subtitle Interaction** -- Multi-select mode, time micro-adjustment (±0.1s), merge/split segments, global search & replace.
- **Waveform Visualization** -- Canvas-based waveform display with segment overlays and playhead tracking.
- **Video Preview** -- Built-in player with subtitle overlay, edited-mode jump-cut playback, and proxy generation for large files.

### Export

- **MP4** -- Fast stream copy (`-c copy`) or precise re-encode with hardware encoder support (NVENC / VideoToolbox / QSV / AMF) and codec-presets registry (v2.3.0).
- **Audio / SRT / VTT** -- Standalone audio m4a, subtitle SRT, and WebVTT exports.
- **Timeline formats** -- OTIO, EDL, FCPXML, Premiere XML. Audio-only projects (fps=0) now produce valid timeline files (v2.3.1 P0 fix).
- **Highlight export** -- Export only the highlight ranges to MP4 / audio / SRT / VTT (v2.2.0).

### Data Fidelity & Reliability (v3.0.0)

- **Word-level timestamps preserved end-to-end** -- transcription no longer round-trips through SRT; split/merge maintain word data, and LLM corrections re-align word timings (local edits keep original timestamps, unreliable alignments are cleared rather than misplaced).
- **Crash-safe project files** -- atomic saves with fsync + rotating `.bak.1/.bak.2` backups; corrupted projects auto-recover with a toast and self-heal on disk.
- **LLM reliability protocol** -- batch ledger with retry and coverage-gap surfacing (never silently drops a batch), response sanitization, SSRF guard on base URLs, opaque segment ids, per-path temperature control.
- **Waveform peak cache** -- `<media>.peaks.json` sidecar with a `{size, mtime_ms}` signature; reopening the same media is ready in ~1 ms instead of re-running ffmpeg.

### Performance & Scale (v3.0.0)

- **Layered undo** -- per-layer snapshots via the backend `apply_undo` channel; undo on a 1167-segment project costs ~1.2 ms on the main thread with a strictly increasing revision.
- **Virtualized transcript list + in-place patch merging** -- 1200-segment projects scroll at 60 fps; unchanged rows keep object identity so Vue skips re-rendering them.
- **Batched bridge events + adaptive tick** -- one `evaluate_js` per batch (512 KB budget), idle tick drops to 250 ms; waveform generation no longer blocks the UI thread.
- **Waveform rendering pipeline** -- rAF-coalesced draws, DPR-aware canvas resizing, imperative playhead (zero Vue patches during playback), hover seek preview.

### Multi-Track Subtitles (v3.0.0 MVP)

- **Extension tracks** -- import an SRT as a read-only second track with automatic 300 ms-tolerance binding to the main track; collapsible track lane in the timeline; per-track SRT export at original timestamps.
- **Workflow failure rollback** -- per-step layer snapshots persisted cross-session; when a workflow step fails you can roll back just that step (keeping earlier steps) or the whole workflow.

### Platform & Local-First

- **Local-first** -- All processing happens on your machine. No data leaves your device. LLM calls go directly from the desktop app to your configured provider.
- **macOS cold-start fix** -- `__BRIDGE_READY__` signal eliminates the pywebview race that caused blank pages on first launch (v2.2.1).
- **ProjectPatch protocol** -- Layer-scoped partial updates (segments / edits / analysis) replace the legacy full-Project dump, cutting wire payload by ~70% and reducing p95 write latency by up to 81% on long projects (v2.3.2).

> **已知限制**: 工作流模式有待充分验证。详见 [docs/2.1.1/release-2.1.1.md](docs/2.1.1/release-2.1.1.md).

## Quick Start

### Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) package manager
- [Bun](https://bun.sh/) (for frontend)
- FFmpeg & FFprobe (must be in PATH or configured in settings)

### Development

```bash
# One-click launch (installs deps, starts Vite dev server + PyWebView window)
uv run dev.py

# Or with pre-built frontend_dist/
uv run dev.py --no-vite

# Install dependencies only
uv run dev.py --setup
```

### Build

```bash
uv run build.py              # Build desktop app (onedir)
uv run build.py --onefile    # Build single executable
uv run build.py --clean      # Clean artifacts first
```

### Test

```bash
# Backend (pytest, 478 tests)
uv run pytest tests/ -v

# Frontend (vitest, 241 tests)
cd frontend && bun run test

# Type-check + production build (vue-tsc + vite build)
cd frontend && bun run build
```

### Performance Baselines (v2.3.2)

```bash
# Generate a deterministic synthetic project (1167 segments / 989 edits / 490 KB)
uv run python -m tests.fixtures.generate_synthetic_project \
    --output /tmp/synthetic.json --segments 1167 --edits 989

# Run backend benchmark (model_dump, write operations, payload size)
uv run python -m tests.perf.backend_benchmark \
    --runs 30 --output tests/perf/results/baseline.json
```

See [`tests/perf/README.md`](tests/perf/README.md) for the v2.3.2 baseline numbers and how to interpret them.

## Architecture

```
milo-cut/
  main.py              # Entry point + @expose API bridge (~80 methods)
  core/                # Python backend services
    project_service.py # Project CRUD, segment/edit/analysis ops, _revision counter
    project_patch.py   # v2.3.2 ProjectPatch schema + apply_project_patch
    export_service.py  # FFmpeg segment-concat export + highlight virtual edits
    export_timeline.py # OTIO/EDL/FCPXML/Premiere XML timeline export
    ffmpeg_service.py  # ffprobe/ffmpeg wrappers: probing, silence, waveform, proxy
    ffmpeg_presets.py  # Encoder registry (CRF/CQ/QP, pixel format, hardware accel)
    llm_service.py     # LLM provider abstraction (OpenAI/Ollama/custom)
    llm_prompts.py     # System prompts with template variable injection
    llm_presets.py     # Style presets for LLM prompts
    workflow_engine.py # Multi-step workflow orchestration (silence + smart delete + correction)
    analysis_service.py# Rule-based filler word + error-trigger detection
    subtitle_service.py# SRT parsing (UTF-8, GB18030, BOM)
    timeline_utils.py  # Timeline helpers, partial_delete hint collection
    diff_service.py    # Subtitle correction diff generation
    task_manager.py    # Background tasks with progress + cancellation
    bridge_service.py  # HTTP bridge API (health, analyze endpoints)
    media_server.py    # Local HTTP server for video streaming to <video>
    asr_service.py     # ASR plugin abstraction (faster-whisper, qwen3-asr)
    plugin_manager.py  # ASR plugin install / model download lifecycle
    proxy_manager.py   # Proxy video generation for large source files
    config.py          # Settings storage (data/settings.json)
    paths.py           # Cross-platform path resolution
    events.py          # Event name constants (mirror frontend/src/utils/events.ts)
    models.py          # Pydantic v2 frozen models (Project, Segment, EditDecision, ...)
    logging.py         # Loguru setup
  pywebvue/            # Custom pywebview bridge framework
    bridge.py          # Bridge base class + @expose decorator
    app.py             # PyWebView window + __BRIDGE_READY__ signal
  frontend/            # Vue 3 + TypeScript SPA
    src/
      bridge.ts        # Python <-> JS comm (waitForPyWebView, call, onEvent)
      types/project.ts # Project / ProjectPatch / ProjectResponse types
      utils/projectPatch.ts     # applyProjectPatch merge helper
      utils/segmentHelpers.ts   # buildSegmentStateMap, resolveSegmentState
      utils/editedPlayback.ts   # jump-cut playback, delete range resolution
      pages/           # WelcomePage, WorkspacePage, ExportPage
      components/      # waveform/, workspace/, export/, common/
      composables/     # useProject, useEdit, useSegmentEdit, useUndoRedo,
                       # useExport, useAnalysis, useEditedPlayback, useLlmTasks ...
  tests/
    fixtures/          # Synthetic project generator (deterministic)
    perf/              # Backend benchmark harness + results/
    test_*.py          # 478 pytest tests
```

**Communication**: Python `@expose` methods are callable from JS via `bridge.call()`. Python pushes events to frontend via `_emit()`, received with `onEvent()`. The bridge uses a 50ms tick loop because PyWebView restricts `evaluate_js` to the main thread.

**ProjectPatch protocol (v2.3.2)**: Migrated write methods return a `ProjectPatch` envelope (`{revision, segments?, edits?, analysis?, media?, full_project?}`) instead of the full Project dump. The frontend applies patches via `applyProjectPatch`, rejects stale patches via `lastSeenRevision`, and falls back to the legacy full-Project path for unmigrated methods. Layer references stay stable across unrelated mutations, eliminating the Vue cascade that caused the GUI lag reported in v2.3.1.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | pywebview |
| Backend | Python 3.11, Pydantic v2, Loguru |
| Frontend | Vue 3, TypeScript, Vite 6 |
| UI | TailwindCSS v4, DaisyUI v5 |
| AI / LLM | OpenAI-compatible API (DeepSeek, OpenAI, Qwen, GLM, Ollama, custom) |
| ASR | faster-whisper, qwen3-asr (optional plugins) |
| Media processing | FFmpeg / FFprobe |
| Packaging | PyInstaller |

## Target Users

| User type | Typical footage | Core pain point |
|-----------|-----------------|-----------------|
| Knowledge vloggers | 30-90 min talking-head | Stumbles, pauses, repetitions |
| Course / training creators | 45-120 min screen + narration | Re-takes, long pauses |
| Podcast / interview editors | 60-180 min multi-speaker | Finding highlights, removing filler |
| Enterprise training editors | 30-60 min internal recordings | Privacy-sensitive, must stay local |
| Live-stream clipping ops | 2-6 hr streams | Finding peak moments, bulk trimming |

## Version History (since v2.1.1)

| Version | Type | Highlights |
|---------|------|-----------|
| **v2.3.2** | Performance Fix | ProjectPatch layer-update protocol (5 write methods migrated); backend sort invariant; `mergedSegments` simplification; SubtitleOverlay seeked fix. write p50 -38..-45%, p95 up to -81%. |
| **v2.3.1** | Hotfix + audit | audio-only OTIO/EDL/XML empty file (P0); `get_edit_summary` PENDING vs CONFIRMED mismatch; `subtitle_trim` edits created as PENDING; edited jump-cut playback performance audit. |
| **v2.3.0** | Hotfix | Silence detection no longer wipes `AnalysisData` (P0); respects prior user / LLM decisions; LLM re-run respects user edits; overlapping silence edit migration. |
| **v2.2.1** | Bug fix | macOS first-launch blank pages -- `__BRIDGE_READY__` signal fixes pywebview race (#431); SettingsModal lazy mount; defensive `call()` ready check. |
| **v2.2.0** | Features | Subtitle correction ingests `partial_delete` hints from smart delete; highlight export pipeline (MP4 / audio / SRT / VTT) via virtual edits; LLM-unconfigured UX guidance. |
| **v2.1.1** | Features + fixes | Multi-select mode, time micro-adjust, prompt presets, encoder registry. (Baseline for this README update.) |

Full release notes live under `docs/<version>/` (e.g. [`docs/2.3.0/2.3.2-record.md`](docs/2.3.0/2.3.2-record.md)).

## Documentation

- [`docs/design-spec.md`](docs/design-spec.md) -- Apple Edition design language
- [`docs/backend-guide.md`](docs/backend-guide.md) / [`docs/frontend-guide.md`](docs/frontend-guide.md) -- Developer guides
- [`docs/<version>/`](docs/) -- Per-version implementation records (v0.1.0 through v2.3.2)
- [`tests/TEST_GUIDE.md`](tests/TEST_GUIDE.md) -- Automated + manual test procedures
- [`tests/perf/README.md`](tests/perf/README.md) -- Performance baseline harness
- [`AGENTS.md`](AGENTS.md) -- Agent guidance (Codex / Claude Code / OpenCode)

## License

[GPL-3.0](LICENSE)
