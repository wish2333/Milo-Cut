# Milo-Cut Test Guide

## Overview

Milo-Cut uses two test frameworks:
- **Backend (Python)**: pytest with 64 tests across 5 modules
- **Frontend (TypeScript/Vue)**: Vitest with happy-dom, 23 tests across 3 component files

## Prerequisites

```bash
# Backend: Python 3.11+ with uv
uv sync

# Frontend: Node/Bun
cd frontend && bun install
```

## Automated Testing

### Backend Tests

```bash
# Run all backend tests
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ --cov=core --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_models.py -v

# Run tests matching keyword
uv run pytest tests/ -k "filler" -v
```

Backend test modules:

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 15 | Segment, EditDecision, AnalysisResult, Project models |
| `test_analysis_service.py` | 11 | Filler detection, error detection, full analysis |
| `test_subtitle_service.py` | 14 | SRT parsing, validation, multi-encoding |
| `test_project_service.py` | 18 | CRUD, merge/split, search-replace, batch edits, settings |
| `test_config.py` | 5 | Load/save, atomic write, corruption recovery |

### Frontend Tests

```bash
# Run all frontend tests
cd frontend && bun run test

# Watch mode (re-run on change)
cd frontend && bun run test:watch

# Coverage report
cd frontend && bun run test:coverage
```

Frontend test modules:

| File | Tests | Coverage |
|------|-------|----------|
| `TranscriptRow.test.ts` | 8 | Rendering, click-to-seek, inline editing, status badges |
| `SilenceRow.test.ts` | 6 | Duration display, status colors, click-to-seek |
| `EditSummaryModal.test.ts` | 9 | Visibility, hero stats, warnings, confirm/cancel events |

### Running All Tests

```bash
# Backend
uv run pytest tests/ -v

# Frontend
cd frontend && bun run test
```

## Manual Testing

### 1. Application Launch

```bash
# Start the app
uv run python main.py
```

Verify:
- App window opens with welcome screen
- Recent projects list loads (empty on first run)
- Settings are accessible

### 2. Project Import

1. Click "Open Project" or drag-drop a video file
2. Verify: project appears in workspace with video player and empty transcript

### 3. SRT Import

1. Click "Import SRT" in the toolbar
2. Select an SRT file (UTF-8, GB18030, or UTF-8-BOM encoded)
3. Verify: transcript rows appear with timestamps and text
4. Verify: segment IDs are sequential (seg-0001, seg-0002, ...)

### 4. Silence Detection

1. Click "Run Silence Detection" in the toolbar
2. Wait for FFmpeg analysis to complete
3. Verify: silence rows appear between transcript segments
4. Verify: silence segments show duration labels (e.g., "静音 2.5s")

### 5. Filler Word Detection

1. Click "Analysis" dropdown -> "Filler Detection"
2. Verify: suggestion panel shows detected filler words
3. Verify: each result has segment text, time range, and confidence score
4. Verify: Chinese filler words detected (嗯, 啊, 那个, 就是, 然后, etc.)

### 6. Error Trigger Detection

1. Click "Analysis" dropdown -> "Error Detection"
2. Verify: suggestion panel shows detected error triggers
3. Verify: lookahead context (3 segments) is considered
4. Verify: trigger words detected (不对, 重来, 说错了, 这段不要, etc.)

### 7. Full Analysis

1. Click "Analysis" dropdown -> "Full Analysis"
2. Verify: both filler and error results appear in suggestion panel
3. Verify: results are grouped by type (filler/error/silence)

### 8. Subtitle Editing

**Inline text editing:**
1. Double-click a transcript row
2. Modify text in the input field
3. Press Enter or click outside to save
4. Verify: text updates in the transcript list

**Merge segments:**
1. Select two adjacent segments
2. Click "Merge" or use the context menu
3. Verify: segments merge into one with combined text

**Split segment:**
1. Select a segment
2. Click "Split" at the desired position
3. Verify: segment splits into two with correct timestamps

**Search and replace:**
1. Press Ctrl+F to open search bar
2. Enter search query and replacement text
3. Select scope (all segments or selected)
4. Click "Replace"
5. Verify: matching text is replaced and count is shown

### 9. Batch Edit Decisions

1. In the suggestion panel, click "Confirm All" to mark all suggestions for deletion
2. Verify: all suggestion rows change to confirmed status (red/strikethrough)
3. Click "Reject All" to dismiss all suggestions
4. Verify: all suggestion rows change to rejected status (green)
5. Verify: individual confirm/reject buttons work on each suggestion

### 10. Export Summary

1. Click "Export" in the toolbar
2. Verify: EditSummaryModal appears with hero statistics
   - Predicted duration (预计时长)
   - Deletion duration (裁剪掉时长)
   - Deletion percentage (占比)
3. If deletion > 40%: verify red warning text appears
4. If warnings exist: verify warning list with yellow background
5. Click "Confirm Export" to proceed or "Return to Check" to cancel

### 11. Settings

1. Open settings panel
2. Modify ffmpeg/ffprobe paths
3. Adjust silence threshold (dB) and minimum duration
4. Add/remove filler words and error trigger words
5. Verify: settings persist after app restart

### 12. Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+F` | Open search-replace bar |
| `Escape` | Close search bar / cancel modal |
| `Delete` | Mark selected segment for deletion |
| `Space` | Preview audio at selected timestamp |
| `Enter` | Confirm inline edit |
| `Double-click` | Enable inline text editing |

## Troubleshooting

### Backend test failures

```bash
# Check Python version
uv run python --version

# Reinstall dependencies
uv sync --reinstall

# Run with verbose output
uv run pytest tests/ -v --tb=long
```

### Frontend test failures

```bash
# Check Node version
node --version

# Clear cache and reinstall
cd frontend
rm -rf node_modules
bun install

# Run with verbose output
cd frontend && bun run test --reporter=verbose
```

### Build verification

```bash
# Backend: verify module imports
uv run python -c "from main import MiloCutApi; print('OK')"

# Frontend: type check + build
cd frontend && bun run build
```
