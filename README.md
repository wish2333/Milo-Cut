# Milo-Cut

> Turn 1 hour of raw footage into 40 minutes of clean, editable material. Edit video like editing a document.

Milo-Cut is a local-first AI video preprocessing tool for oral presentation videos. It automatically detects silence, filler words, verbal stumbles, and repeated segments -- then lets you confirm and export clean footage. No cloud upload required.

## Features

- **Silence Detection** -- FFmpeg-powered silence detection with configurable threshold and duration
- **Filler Word Detection** -- customizable word list to flag verbal fillers ("um", "uh", etc.)
- **Verbal Stumble Detection** -- triggers on phrases like "wait no", "let me redo that"
- **SRT Import & Editing** -- import existing subtitles, edit text inline, delete segments by removing text
- **Waveform Visualization** -- canvas-based waveform display with segment overlays
- **Video Preview** -- built-in video player with subtitle overlay and playback controls
- **Export** -- MP4 (fast copy or precise re-encode), SRT, OTIO, EDL, FCPXML/Premiere XML
- **Search & Replace** -- batch find/replace across all subtitle text
- **Local-first** -- all processing happens on your machine, no data leaves your device

## Quick Start

### Prerequisites

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) package manager
- [Bun](https://bun.sh/) (for frontend)
- FFmpeg & FFprobe (must be in PATH or configured in settings)

### Development

```bash
# One-click launch (installs deps, starts dev server + desktop window)
dev.bat          # Windows
./dev.sh         # macOS/Linux

# Or manually:
uv run python main.py
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
  main.py              # Entry point + API bridge (~30 exposed methods)
  core/                # Python backend services
    project_service.py # Project CRUD, segment editing, persistence
    export_service.py  # FFmpeg-based video/audio/SRT export
    ffmpeg_service.py  # ffprobe/ffmpeg wrappers, silence/waveform
    analysis_service.py# Filler word & error trigger detection
    subtitle_service.py# SRT parsing (UTF-8, GB18030, BOM)
    task_manager.py    # Background tasks with progress & cancellation
    media_server.py    # Local HTTP server for video streaming
    models.py          # Pydantic v2 data models
  pywebvue/            # Custom pywebview bridge framework
  frontend/            # Vue 3 + TypeScript SPA
    src/
      bridge.ts        # Python <-> JS communication layer
      pages/           # WelcomePage, WorkspacePage
      components/      # Waveform editor, transcript rows, timeline
      composables/     # useProject, useEdit, useExport, useAnalysis...
```

**Communication**: Python `@expose` methods are callable from JS via `bridge.call()`. Python pushes events to frontend via `_emit()`, received with `onEvent()`.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | pywebview |
| Backend | Python 3.11, Pydantic v2, Loguru |
| Frontend | Vue 3, TypeScript, Vite 6 |
| UI | TailwindCSS v4, DaisyUI v5 |
| Media processing | FFmpeg / FFprobe |
| Packaging | PyInstaller |

## License

[GPL-3.0](LICENSE)
