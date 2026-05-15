# WaveformEditor Implementation Plan

> **Generated:** 2026-05-15
> **Status:** Pre-implementation review
> **Replaces:** `src/components/workspace/TimelineRuler.vue` (847 lines)

---

## Context

The current `TimelineRuler.vue` is monolithic, mixing view navigation, zoom, selection, snap,
scrollbar, and segment block rendering into a single 847-line file. The expert UI/UX audit
recommends a complete rewrite into a layered `WaveformEditor.vue` architecture with Canvas
waveform, shared composables, and centralized segment editing.

---

## Phase 1 -- Extract Shared Logic (no UI changes)

### Step 1.1 -- Create `segmentHelpers.ts`

**File:** `frontend/src/utils/segmentHelpers.ts` (~45 lines)

Extract the following pure functions from `TimelineRuler.vue` (lines 495-524) and `Timeline.vue`
(lines 32-63), deduplicating identical implementations:

| Function | Source |
|---|---|
| `isOverlapping(edit, seg)` | Both files |
| `getEditForSegment(seg, edits)` | Both files |
| `getEffectiveStatus(seg, edits)` | Both files |
| `getEditStatus(seg, edits)` | Both files |

All functions are pure, accept `Segment` / `EditDecision` typed parameters, and have no
side effects.

---

### Step 1.2 -- Create `useTimelineMetrics.ts`

**File:** `frontend/src/composables/useTimelineMetrics.ts` (~180 lines)

Extract from `TimelineRuler.vue` and expose as a composable:

**View state:**
- `viewStart: Ref<number>`
- `viewDuration: Ref<number>`
- `viewEnd: ComputedRef<number>`

**Time/pixel conversion:**
- `timeToPercent(time)` -> `number`
- `percentToPixels(pct)` -> `number`
- `getTimeFromX(clientX)` -> `number`

**Zoom:**
- `zoomAt(focalTime, factor)`
- `handleWheel(e: WheelEvent)`

**Scroll:**
- `clampViewStart(raw)` -> `number`
- `scrollTo(time)`

**Playhead follow:**
- `maybeFollowPlayhead(currentTime)`
- `ensurePlayheadInView(currentTime)`
- `playheadPercent: ComputedRef<number>`

**Scrollbar geometry:**
- `thumbLeft: ComputedRef<number>`
- `thumbWidth: ComputedRef<number>`

**Time marks:**
- `timeMarks: ComputedRef<{ time: number; label: string }[]>`

**Interface:** accepts `Ref<number>` for `duration` and `currentTime`, plus a `containerRef`.

**Constants preserved:**

```typescript
const MIN_VIEW_DURATION = 2      // seconds
const MAX_VIEW_DURATION = 600    // seconds
const ZOOM_IN_FACTOR   = 0.87
const ZOOM_OUT_FACTOR  = 1.15
```

---

### Step 1.3 -- Create `useSegmentEdit.ts`

**File:** `frontend/src/composables/useSegmentEdit.ts` (~130 lines)

Centralized segment editing composable, consumed by both `WorkspacePage` (as provider) and child
components (via props or inject).

**Editing operations:**

| Method | Sync | Backend call |
|---|---|---|
| `updateTime(segId, field, value)` | Optimistic local update | Debounced 300 ms -> `call("update_segment")` |
| `updateText(segId, text)` | Immediate | Immediate -> `call("update_segment")` |
| `toggleEditStatus(segId)` | Immediate | Immediate |

**Selection state:**
- `selectedSegmentId: Ref<string | null>`
- `selectedRange: Ref<{ start: number; end: number } | null>`

**Status queries:** delegate to `segmentHelpers.ts`, not reimplemented here.

---

### Step 1.4 -- Wire helpers into existing components

**Modify `Timeline.vue`:** replace inline helpers (lines 32-63) with imports from
`segmentHelpers.ts`. No behavior change.

**Modify `TimelineRuler.vue`:** replace inline helpers (lines 495-524) with imports from
`segmentHelpers.ts`. No behavior change.

No visual output changes. This step is purely deduplication.

---

### Step 1.5 -- Unit tests for Phase 1

| File | Lines | Coverage |
|---|---|---|
| `src/utils/segmentHelpers.test.ts` | ~80 | All 4 helper functions, edge cases |
| `src/composables/useTimelineMetrics.test.ts` | ~120 | Zoom, scroll, clamp, pixel conversion |
| `src/composables/useSegmentEdit.test.ts` | ~100 | Optimistic update, debounce, selection |

**Verify:** `bun run test` passes, existing UI unchanged.

---

## Phase 2 -- WaveformEditor Shell (feature-flagged)

### Step 2.1 -- Create `WaveformEditor.vue`

**File:** `frontend/src/components/waveform/WaveformEditor.vue` (~200 lines)

Drop-in replacement for `TimelineRuler.vue` -- same props/emits interface.

Internally instantiates `useTimelineMetrics` and `provide`s it to child layers via typed
`InjectionKey`.

**Template structure:**

```
<div class="flex flex-col">
  <!-- Controls bar: zoom buttons, time display -->
  <div class="h-6 ...">...</div>

  <!-- Layer container: position: relative, h-28 -->
  <div class="relative h-28 overflow-hidden" ref="containerRef">
    <WaveformCanvas     style="z-index: 0; pointer-events: none" />
    <TimeMarksLayer     style="z-index: 1; height: 24px; top: 0" />
    <SegmentBlocksLayer style="z-index: 2; pointer-events: all" />
    <PlayheadOverlay    style="z-index: 10; pointer-events: none" />
  </div>

  <!-- Scrollbar -->
  <ScrollbarStrip />
</div>
```

**Layer z-index stack (bottom -> top):**

| z | Layer | pointer-events |
|---|---|---|
| 0 | `WaveformCanvas` | none |
| 1 | `TimeMarksLayer` | click-to-seek strip only |
| 2 | `SegmentBlocksLayer` | all |
| 10 | `PlayheadOverlay` | none |

---

### Step 2.2 -- Create `TimeMarksLayer.vue`

**File:** `frontend/src/components/waveform/TimeMarksLayer.vue` (~60 lines)

- Injects `useTimelineMetrics` from parent
- Renders time labels + tick lines from `timeMarks` computed
- `mousedown` on the top 24 px strip emits `seek`

---

### Step 2.3 -- Create `SegmentBlocksLayer.vue`

**File:** `frontend/src/components/waveform/SegmentBlocksLayer.vue` (~200 lines)

**`visibleBlocks` computed:** filters segments to `[viewStart, viewEnd]`, clamps display
boundaries, computes `leftPercent` and `widthPercent` for each block.

**Interaction zones per block:**

| Zone | Width | Cursor | Action |
|---|---|---|---|
| Left handle | 16 px hit / 8 px visual | `ew-resize` | Resize `start` |
| Right handle | 16 px hit / 8 px visual | `ew-resize` | Resize `end` |
| Body | remaining | `grab` | Move selection |
| Empty space | -- | default | Create new range selection |

**Edge drag behaviour:**
- On `mousemove`: optimistic local update via `useSegmentEdit.updateTime`
- On `mouseup`: snap to frame boundary, then debounced backend sync
- Constraint: `start < end - 0.1 s` enforced during drag via `clampTime`

**Snap:** only on `mouseup`, not during drag (avoids jump artefacts).

```typescript
const MIN_SEGMENT_DURATION = 0.1   // seconds
const EDGE_HANDLE_HIT_PX   = 16
const EDGE_HANDLE_VISUAL_PX = 8
```

---

### Step 2.4 -- Create `PlayheadOverlay.vue`

**File:** `frontend/src/components/waveform/PlayheadOverlay.vue` (~30 lines)

- Red vertical line + downward triangle marker at `playheadPercent`
- `pointer-events: none`
- Injects metrics from parent

---

### Step 2.5 -- Create `ScrollbarStrip.vue`

**File:** `frontend/src/components/waveform/ScrollbarStrip.vue` (~50 lines)

- Custom scrollbar thumb, extracted from `TimelineRuler.vue` lines 441-468
- Thumb position/width from injected `thumbLeft` / `thumbWidth`
- Drag to pan view

---

### Step 2.6 -- Create `WaveformCanvas.vue` (stub)

**File:** `frontend/src/components/waveform/WaveformCanvas.vue` (~40 lines, grows to ~150 in
Phase 4)

Phase 2 stub: `<canvas>` element filled with a flat gray gradient placeholder.
`pointer-events: none`. Full implementation deferred to Phase 4.

---

### Step 2.7 -- Feature flag in `WorkspacePage.vue`

```typescript
const useNewWaveformEditor = ref(false)
// Toggle: Ctrl+Shift+W
```

```html
<WaveformEditor v-if="useNewWaveformEditor" ... />
<TimelineRuler  v-else                      ... />
```

**Verify:** `Ctrl+Shift+W` toggles between old and new without console errors. New shell renders
all layers at correct z-index.

---

## Phase 3 -- Edge Drag + Bidirectional Sync

### Step 3.1 -- Wire `useSegmentEdit` into `WorkspacePage`

- Replace `handleUpdateTime` / `handleToggleEditStatus` with `useSegmentEdit` methods
- Remove local `selectedSegmentId` / `selectedRange` refs (now owned by `useSegmentEdit`)

### Step 3.2 -- Segment edge drag in `SegmentBlocksLayer`

Full implementation of the interaction zones defined in Step 2.3:

```typescript
function handleBlockEdgeMouseDown(
  segId: string,
  edge: "left" | "right",
  e: MouseEvent,
) {
  e.stopPropagation()
  const seg = segments.find(s => s.id === segId)!
  const initialValue = edge === "left" ? seg.start : seg.end
  const offset = initialValue - getTimeFromX(e.clientX)

  const onMove = (e: MouseEvent) => {
    const raw = getTimeFromX(e.clientX) + offset
    const clamped = clampTime(raw, edge, seg)
    updateTime(segId, edge === "left" ? "start" : "end", clamped)
  }

  const onUp = (e: MouseEvent) => {
    const raw = getTimeFromX(e.clientX) + offset
    const snapped = snapToFrame(clampTime(raw, edge, seg))
    updateTime(segId, edge === "left" ? "start" : "end", snapped)
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }

  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}
```

### Step 3.3 -- Bidirectional sync

```
TranscriptRow edit  ->  useSegmentEdit.updateTime
                    ->  segments ref (single source of truth)
                    ->  WaveformEditor receives updated prop  OK

WaveformEditor drag ->  useSegmentEdit.updateTime
                    ->  segments ref
                    ->  Timeline receives updated prop        OK
```

No event bus. No manual cross-component notification. Vue reactivity handles propagation.

**Verify:** Edit `start` in `TranscriptRow` -> block moves in `WaveformEditor`. Drag block edge
-> time updates in `TranscriptRow`.

---

## Phase 4 -- Canvas Waveform + Silence Overlay

### Step 4.1 -- Implement `WaveformCanvas` rendering

Grow `WaveformCanvas.vue` from stub (~40 lines) to full implementation (~150 lines).

- Load pre-computed peak data from `project.media.waveform_path`
- Expected data format: JSON array of `{ min: number; max: number }` per pixel bucket
- Draw filled polygon: top peaks + mirrored bottom peaks, single `lineTo` path
- Color: `#94a3b8` (slate-400) fill, `#64748b` (slate-500) stroke
- `ResizeObserver` triggers redraw on container width change
- Viewport-only rendering: only draw peaks within `[viewStart, viewEnd]`
- Fallback: flat line at midpoint when `waveform_path` is absent or load fails

### Step 4.2 -- Silence overlay on Canvas

Rendered in the same `requestAnimationFrame` pass as the waveform -- no extra DOM layer needed.

```typescript
// After drawing waveform
for (const sil of silenceSegments) {
  const x = timeToPixel(sil.start)
  const w = timeToPixel(sil.end) - x
  ctx.fillStyle = "rgba(148, 163, 184, 0.25)"   // slate-400 @ 25%
  ctx.fillRect(x, 0, w, canvas.height)
}
```

Visual result: waveform is naturally flat in silence areas (audio signal) + light overlay provides
explicit system annotation. No separate DOM overlay layer required.

**Verify:** Waveform renders with peak data. Silence areas show flat waveform + overlay. Zooming
redraws correctly.

---

## Phase 5 -- Delete Old Code + Tests

### Step 5.1 -- Remove feature flag, delete `TimelineRuler.vue`

- `WorkspacePage.vue`: remove `useNewWaveformEditor` ref and `v-if/v-else`, always render
  `<WaveformEditor>`
- Delete `src/components/workspace/TimelineRuler.vue`

### Step 5.2 -- Interaction tests for `SegmentBlocksLayer`

**File:** `frontend/src/components/waveform/SegmentBlocksLayer.test.ts` (~150 lines)

```
- edge drag: left handle moves start, right handle moves end
- body drag: both start and end move by same delta
- new selection: click on empty space creates selectedRange
- snap on mouseup: final value aligned to frame boundary
- min duration: cannot drag start past (end - 0.1s)
- 16px hit zone: click 7px from edge registers as edge drag
- 9px from edge registers as body drag
```

### Step 5.3 -- Manual test checklist

| Behaviour | Expected |
|---|---|
| `Ctrl+Scroll` | Zoom in/out centred on cursor |
| Plain scroll | Pan timeline left/right |
| Click timecode strip | Seek to clicked time |
| Click segment block body | Select block, emit `select-range` |
| Drag block left edge | `start` updates, block resizes |
| Drag block right edge | `end` updates, block resizes |
| Release near segment boundary | Snaps to neighbour boundary |
| Block cannot be smaller than 100 ms | Drag clamped |
| Playhead auto-follow during playback | View pans to keep playhead visible |
| Scrollbar thumb drag | Pans view proportionally |
| Edit time in `TranscriptRow` | Block moves in `WaveformEditor` |
| Drag block edge | Time updates in `TranscriptRow` |
| `bun run test` | All tests pass |

---

## Files Summary

### New files (12)

| File | Lines | Purpose |
|---|---|---|
| `src/utils/segmentHelpers.ts` | ~45 | Shared segment/edit helpers |
| `src/utils/segmentHelpers.test.ts` | ~80 | Helper unit tests |
| `src/composables/useTimelineMetrics.ts` | ~180 | Time/pixel math + view state |
| `src/composables/useTimelineMetrics.test.ts` | ~120 | Metrics unit tests |
| `src/composables/useSegmentEdit.ts` | ~130 | Centralized edit + debounce |
| `src/composables/useSegmentEdit.test.ts` | ~100 | Edit unit tests |
| `src/components/waveform/WaveformEditor.vue` | ~200 | Layer orchestrator |
| `src/components/waveform/TimeMarksLayer.vue` | ~60 | Time marks + tick lines |
| `src/components/waveform/SegmentBlocksLayer.vue` | ~200 | Blocks + drag interaction |
| `src/components/waveform/WaveformCanvas.vue` | ~150 | Canvas waveform + silence overlay |
| `src/components/waveform/PlayheadOverlay.vue` | ~30 | Red playhead line |
| `src/components/waveform/ScrollbarStrip.vue` | ~50 | Custom scrollbar |

### Modified files (2)

| File | Change |
|---|---|
| `src/pages/WorkspacePage.vue` | Feature flag (Phase 2), `useSegmentEdit` integration (Phase 3) |
| `src/components/workspace/Timeline.vue` | Replace inline helpers with `segmentHelpers.ts` imports |

### Deleted files (1, Phase 5)

| File | Reason |
|---|---|
| `src/components/workspace/TimelineRuler.vue` | Replaced by `WaveformEditor` |

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Canvas performance on long videos | Pre-computed peak data; viewport-only rendering; no redraw outside `[viewStart, viewEnd]` |
| Edge drag debounce lag feels unresponsive | Optimistic local update is immediate; only backend sync is debounced |
| Bidirectional sync causes infinite update loops | Single source of truth (`segments` ref in `WorkspacePage`); props flow strictly downward; no component writes to a ref it received as a prop |
| `provide`/`inject` coupling makes testing hard | Typed `InjectionKey`; each layer accepts metrics as optional prop fallback for unit tests |
| Phase 5 deletion breaks something not caught by tests | Feature flag kept until all manual checklist items pass |

---

## Dependency Graph

```
WorkspacePage
  +-- useSegmentEdit          <-- owns segments write operations
  +-- WaveformEditor
  |     +-- useTimelineMetrics  (provide -> inject into all layers)
  |     +-- WaveformCanvas      (inject metrics)
  |     +-- TimeMarksLayer      (inject metrics)
  |     +-- SegmentBlocksLayer  (inject metrics + useSegmentEdit methods via props)
  |     +-- PlayheadOverlay     (inject metrics)
  |     +-- ScrollbarStrip      (inject metrics)
  +-- Timeline
        +-- TranscriptRow       (useSegmentEdit methods via emits -> WorkspacePage)
        +-- SilenceRow          (useSegmentEdit methods via emits -> WorkspacePage)

segmentHelpers.ts  <--  imported by Timeline.vue, useSegmentEdit.ts
useTimelineMetrics <--  instantiated in WaveformEditor, provided to children
useSegmentEdit     <--  instantiated in WorkspacePage, passed down as props/emits
```
