# Milo-Cut v2 Audit Fix Implementation Plan

> Based on `docs/audit-report-preview-2.md` -- 7 HIGH bugs, 4 missing features blocking core workflow.

---

## Phase 1: Critical Bug Fixes + Developer Experience (2-3 days)

### Task 1.1: Fix `getEffectiveStatus` ignoring rejected edits (B1) [HIGH]

- **File**: `frontend/src/utils/segmentHelpers.ts:20-31`
- **Bug**: `getEffectiveStatus` sorts by priority but never checks `status` -- rejected edits still return "masked"
- **Fix**: Filter out `status !== "rejected"` before sorting, then pick top from active list
- **Tests**: Add 3 cases to `segmentHelpers.test.ts` (single rejected, multi-priority fallback, all rejected)
- **Effort**: 1h | **Critical path**: Yes

### Task 1.2: Add `minOverlapSeconds` to `isOverlapping` (A4) [HIGH]

- **File**: `frontend/src/utils/segmentHelpers.ts:3-5`
- **Bug**: Any 1ms overlap marks entire subtitle as "masked"
- **Fix**: Add `minOverlapSeconds` param (default 0.0), pass 0.3 in `getEffectiveStatus` caller
- **Tests**: Add 3 cases (below threshold, above threshold, target_id bypass)
- **Effort**: 30min | **Critical path**: No

### Task 1.3: Add recent projects to WelcomePage (C1) [HIGH]

- **File**: `frontend/src/pages/WelcomePage.vue`
- **Bug**: Only "upload media" flow exists; `useProject.openProject()` + `get_recent_projects` API already implemented but unused
- **Fix**: `onMounted` fetch recent projects, render list, click calls `openProject(path)`
- **Effort**: 4h | **Critical path**: No

### Task 1.4: Add segment deletion (A1) [HIGH]

- **Backend**: Add `delete_segment(segment_id)` to `project_service.py`, expose in `main.py`
- **Frontend**: Add Delete key + right-click menu to `SegmentBlocksLayer.vue`, add `deleteSegment()` to `useEdit.ts`
- **Tests**: Backend `test_delete_segment` + frontend emit test
- **Effort**: 6-8h | **Critical path**: No

### Task 1.5: Fix waveform rendering (A3) [MEDIUM]

- **Backend**: Register `WAVEFORM_GENERATION` handler in `main.py:38-57`, implement ffmpeg peak extraction (100 buckets/sec)
- **Frontend**: Add `duration` prop to `WaveformCanvas.vue`, fix line 866 math: `totalBuckets / duration` instead of `totalBuckets / (vs + vd)`
- **Wire up**: Trigger waveform task after project create/open if `waveform_path` is null
- **Effort**: 4-6h | **Critical path**: No

---

## Phase 2: Project Management Robustness (1 day)

### Task 2.1: Fix silence detection dedup ignoring rejected (B2) [MEDIUM]

- **File**: `core/project_service.py:182-188`
- **Fix**: Add `EditStatus.REJECTED` to `already_covered` check
- **Tests**: Reject edit, re-run detection, verify no overwrite
- **Effort**: 30min

### Task 2.2: Add SRT import validation (C2) [LOW]

- **Files**: `main.py:240-244`, `core/subtitle_service.py`
- **Fix**: Call `validate_srt` before `update_transcript`, handle orphaned EditDecision `target_id` refs
- **Effort**: 1-2h

---

## Phase 3: Core Feature Extensions (3-5 days)

### Task 3.1: Fix `_extract_segment` for audio-only (E1) [HIGH]

- **File**: `core/export_service.py:2493-2517`
- **Fix**: Add `has_video` param, use `-t` instead of `-to`, preset `fast`, conditional codec args
- **Effort**: 3-4h | **Critical path**: Yes (blocks D3)

### Task 3.2: Subtitle-based smart trimming (D1) [HIGH]

- **Backend**: Add `generate_subtitle_keep_ranges(padding=0.3)` to `project_service.py` -- generates EditDecisions for ranges outside subtitle+padding
- **Frontend**: Add `runSubtitleTrim(padding)` composable, wire to UI button
- **Effort**: 6-8h | **Critical path**: Yes (core value proposition)

### Task 3.3: Audio-only export (D3) [LOW]

- Depends on E1. Add `export_audio` to `export_service.py`, `exportAudio()` to `useExport.ts`
- **Effort**: 2-3h

### Task 3.4: Crossfade/silence gap (D2) [MEDIUM]

- Add `crossfade_ms` + `silence_gap_ms` params to export, use ffmpeg `acrossfade` filter
- **Effort**: 4-6h

### Task 3.5: Dual timeline design (A2) [HIGH] -- DEFERRED

- Major refactor (8-12h). The `minOverlapSeconds` fix from 1.2 provides sufficient short-term relief.
- Implement after Phase 1-3 stable + user feedback collected.

### Task 3.6: Output container format (E2) [LOW]

- Parameterize output format (mp4/mkv/webm for video, m4a/mp3/wav for audio)
- **Effort**: 2-3h

---

## Dependency Graph

```
Phase 1 (parallel where possible):
  1.1 (B1) ───┐
  1.2 (A4) ───┤── test together
  1.3 (C1) ───┤── independent
  1.4 (A1) ───┤── independent
  1.5 (A3) ───┘── independent

Phase 2 (fully parallel):
  2.1 (B2) ─── independent
  2.2 (C2) ─── independent

Phase 3 (sequential):
  3.1 (E1) ──┬── 3.2 (D1), 3.3 (D3), 3.4 (D2) depend on this
              └── 3.5 (A2) deferred
  3.6 (E2) ── independent
```

## Critical Path: ~15-18h focused work

1. Task 1.1 (B1) -> 1h
2. Task 1.2 (A4) -> 30min
3. Task 1.3 (C1) -> 4h
4. Task 3.1 (E1) -> 3-4h
5. Task 3.2 (D1) -> 6-8h

## Testing Strategy

- Phase 1: 6 new unit tests in `segmentHelpers.test.ts`, backend tests for `delete_segment`, manual smoke test
- Phase 2: Backend dedup + SRT validation tests
- Phase 3: New `test_export_service.py`, subtitle trim tests, audio export integration test
- Regression: `bun run test` (frontend) + `uv run pytest` (backend) after each phase