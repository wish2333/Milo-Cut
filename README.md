# Milo-Cut

> Turn 1 hour of raw footage into 40 minutes of clean, editable material. Edit video like editing a document -- with AI assistance.

Milo-Cut is a local-first, AI-powered desktop video preprocessing tool for oral presentation videos. It detects silence, analyzes content with LLM for smart trimming, corrects ASR transcription errors, and extracts highlights -- then lets you review and export clean footage. No cloud upload required.

## Features

- **AI Smart Delete** -- LLM analyzes transcript to flag filler words, repeated segments, self-corrections, and off-topic asides for bulk removal
- **AI Subtitle Correction** -- LLM batch-corrects ASR recognition errors with side-by-side diff review
- **AI Highlight Extraction** -- LLM identifies key moments from long recordings for quick navigation
- **Silence Detection** -- FFmpeg-powered silence detection with configurable threshold and duration
- **AI Semantic Search** -- natural language queries to locate specific segments ("find the slide about Q3 revenue")
- **Multi-Timeline Editing** -- manage multiple edit timelines with independent transcript, edits, and analysis
- **Workflow Engine** -- orchestrates silence detection, smart delete, and subtitle correction in a configurable pipeline
- **Prompt Presets & Editing** -- customize LLM system prompts with style presets, template variable injection
- **Subtitle Interaction** -- multi-select mode, time micro-adjustment (+-0.1s), merge/split segments, search & replace
- **Waveform Visualization** -- canvas-based waveform display with segment overlays and playhead tracking
- **Video Preview** -- built-in video player with subtitle overlay, playback controls, and proxy generation
- **Export** -- MP4 (fast copy or precise re-encode), SRT, OTIO, EDL, FCPXML/Premiere XML
- **Local-first** -- all processing happens on your machine, no data leaves your device

> **已知限制**: 精华提取功能的导出管线尚未完成对接，工作流模式有待充分验证。详见 [release-2.1.1.md](release-2.1.1.md#六已知问题)。

## Quick Start

### Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) package manager
- [Bun](https://bun.sh/) (for frontend)
- FFmpeg & FFprobe (must be in PATH or configured in settings)

### Development

```bash
# One-click launch (installs deps, starts dev server + desktop window)
uv run dev.py

# Or with pre-built frontend
uv run dev.py --no-vite
```

### Build

```bash
uv run build.py              # Build desktop app (onedir)
uv run build.py --onefile    # Build single executable
uv run build.py --clean      # Clean artifacts first
```

### Test

```bash
# Backend (pytest)
uv run pytest tests/ -v

# Frontend (vitest)
cd frontend && bun run test
```

## Architecture

```
milo-cut/
  main.py              # Entry point + API bridge (~80+ exposed methods)
  core/                # Python backend services
    project_service.py # Project CRUD, segment editing, persistence
    export_service.py  # FFmpeg-based video/audio/SRT export
    export_timeline.py # OTIO/EDL/FCPXML/Premiere XML timeline export
    ffmpeg_service.py  # ffprobe/ffmpeg wrappers, silence/waveform/proxy
    llm_service.py     # LLM provider abstraction (OpenAI/Ollama/custom)
    llm_prompts.py     # LLM system prompts with template variable injection
    workflow_engine.py # Multi-step workflow orchestration engine
    subtitle_service.py# SRT parsing (UTF-8, GB18030, BOM)
    timeline_utils.py  # Timeline helper utilities
    task_manager.py    # Background tasks with progress & cancellation
    bridge_service.py  # HTTP bridge API (health, analyze endpoints)
    media_server.py    # Local HTTP server for video streaming
    models.py          # Pydantic v2 data models
  pywebvue/            # Custom pywebview bridge framework
  frontend/            # Vue 3 + TypeScript SPA
    src/
      bridge.ts        # Python <-> JS communication layer
      pages/           # WelcomePage, WorkspacePage, ExportPage
      components/      # Waveform editor, transcript rows, AI assistant panel, timeline
      composables/     # useProject, useEdit, useExport, useAnalysis, useLlmTasks...
```

**Communication**: Python `@expose` methods are callable from JS via `bridge.call()`. Python pushes events to frontend via `_emit()`, received with `onEvent()`.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | pywebview |
| Backend | Python 3.11, Pydantic v2, Loguru |
| Frontend | Vue 3, TypeScript, Vite 6 |
| UI | TailwindCSS v4, DaisyUI v5 |
| AI / LLM | OpenAI-compatible API (OpenAI, Ollama, custom providers) |
| Media processing | FFmpeg / FFprobe |
| Packaging | PyInstaller |

## License

[GPL-3.0](LICENSE)
