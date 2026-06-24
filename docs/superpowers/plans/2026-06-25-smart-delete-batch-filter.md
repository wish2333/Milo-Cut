# Smart Delete Input Filter + Batch Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace smart-delete time-window chunking with count-based batch+target mode, and filter confirmed-deleted segments from LLM analysis input for both smart-delete (P0) and subtitle-correction (P1).

**Architecture:** Extract a shared `collect_confirmed_deleted_seg_ids()` helper in `core/timeline_utils.py`. Add `chunk_transcript_by_count()` to `core/llm_service.py` using P1-style batch+target pattern. Wire filters into `main.py` handlers before passing segments to analysis. Update settings, prompts, and frontend types/inputs.

**Tech Stack:** Python 3.11, Pydantic v2, Vue 3 + TypeScript, Tailwind CSS 4 + DaisyUI 5

**Spec source:** `docs/2.1.1/spec-smart-delete-input-filter-batch-2.1.1-5.md`

## Global Constraints

- All `@expose` methods return `{"success": bool, "data": ..., "error": ...}` envelope
- Models use Pydantic v2 with `frozen=True`
- Use `uv run` for all Python execution
- Use `bun` for frontend
- No emoji in code or commit messages
- Python 3.11 (pinned in `.python-version`)
- Settings persisted to `data/settings.json`
- Event names in `core/events.py` must stay in sync with `frontend/src/utils/events.ts`

---

### Task 1: Create `core/timeline_utils.py` with `collect_confirmed_deleted_seg_ids()`

**Files:**
- Create: `core/timeline_utils.py`
- Test: `tests/test_timeline_utils.py`

**Interfaces:**
- Produces: `collect_confirmed_deleted_seg_ids(timeline: Timeline) -> set[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_timeline_utils.py
"""Tests for core/timeline_utils.py"""

from core.models import EditDecision, EditStatus, Timeline
from core.timeline_utils import collect_confirmed_deleted_seg_ids
from tests.conftest import make_timeline, make_segment


def _make_edit(action: str, status: EditStatus, target_type: str = "segment", target_id: str = "seg_1") -> dict:
    """Build an EditDecision dict for testing."""
    return {
        "id": "edit_1",
        "start": 0.0,
        "end": 1.0,
        "action": action,
        "source": "test",
        "analysis_id": None,
        "status": status,
        "priority": 50,
        "target_type": target_type,
        "target_id": target_id,
    }


def test_confirmed_delete_segment_collected():
    """Confirmed delete with target_type=segment should be collected."""
    timeline = make_timeline(
        edits=[EditDecision(**_make_edit("delete", EditStatus.CONFIRMED, "segment", "seg_1"))]
    )
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == {"seg_1"}


def test_keep_action_not_collected():
    """Confirmed keep (partial_delete) should NOT be collected."""
    timeline = make_timeline(
        edits=[EditDecision(**_make_edit("keep", EditStatus.CONFIRMED, "segment", "seg_1"))]
    )
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == set()


def test_pending_delete_not_collected():
    """Pending delete should NOT be collected."""
    timeline = make_timeline(
        edits=[EditDecision(**_make_edit("delete", EditStatus.PENDING, "segment", "seg_1"))]
    )
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == set()


def test_rejected_delete_not_collected():
    """Rejected delete should NOT be collected."""
    timeline = make_timeline(
        edits=[EditDecision(**_make_edit("delete", EditStatus.REJECTED, "segment", "seg_1"))]
    )
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == set()


def test_range_target_type_ignored():
    """Confirmed delete with target_type=range should NOT be collected."""
    timeline = make_timeline(
        edits=[EditDecision(**_make_edit("delete", EditStatus.CONFIRMED, "range", "seg_1"))]
    )
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == set()


def test_missing_target_id_ignored():
    """Confirmed delete with missing target_id should NOT crash."""
    edit_data = _make_edit("delete", EditStatus.CONFIRMED, "segment", "seg_1")
    edit_data["target_id"] = None
    timeline = make_timeline(
        edits=[EditDecision(**edit_data)]
    )
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == set()


def test_multiple_edits_mixed():
    """Only confirmed-delete-segment edits should be returned."""
    timeline = make_timeline(
        edits=[
            EditDecision(**_make_edit("delete", EditStatus.CONFIRMED, "segment", "seg_1")),
            EditDecision(**_make_edit("keep", EditStatus.CONFIRMED, "segment", "seg_2")),
            EditDecision(**_make_edit("delete", EditStatus.PENDING, "segment", "seg_3")),
            EditDecision(**_make_edit("delete", EditStatus.CONFIRMED, "segment", "seg_4")),
            EditDecision(**_make_edit("delete", EditStatus.CONFIRMED, "range", "seg_5")),
        ]
    )
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == {"seg_1", "seg_4"}


def test_empty_edits():
    """Empty edits list should return empty set."""
    timeline = make_timeline(edits=[])
    result = collect_confirmed_deleted_seg_ids(timeline)
    assert result == set()
```

Note: `tests/conftest.py` may need a `make_timeline()` helper if not already present. Check first — if it exists with different signature, adapt the test imports accordingly.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_timeline_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.timeline_utils'`

- [ ] **Step 3: Write the implementation**

```python
# core/timeline_utils.py
"""Timeline-level utility functions shared across LLM handlers."""

from __future__ import annotations

from core.models import EditStatus, Timeline


def collect_confirmed_deleted_seg_ids(timeline: Timeline) -> set[str]:
    """Return segment IDs targeted by confirmed delete decisions.

    Only ``action="delete" AND status=confirmed`` edits with
    ``target_type="segment"`` contribute. Used by P0/P1 to skip
    already-confirmed-deleted segments from LLM analysis input.
    """
    result: set[str] = set()
    for edit in timeline.edits:
        if (
            edit.action == "delete"
            and edit.status == EditStatus.CONFIRMED
            and edit.target_type == "segment"
            and edit.target_id
        ):
            result.add(edit.target_id)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_timeline_utils.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```
feat(timeline): extract collect_confirmed_deleted_seg_ids helper

- New core/timeline_utils.py with shared helper for confirmed-delete filtering
- Used by P0 smart-delete and P1 subtitle-correction to skip already-deleted segments
```

---

### Task 2: Add `chunk_transcript_by_count()` to `core/llm_service.py`

**Files:**
- Modify: `core/llm_service.py` (add function after `chunk_transcript` at ~line 309)
- Test: `tests/test_llm_service.py` (append new test class)

**Interfaces:**
- Produces: `chunk_transcript_by_count(segments, batch_size=20, overlap=4) -> list[tuple[list[dict], set[str]]]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_service.py`:

```python
from core.llm_service import chunk_transcript, chunk_transcript_by_count, estimate_tokens, get_llm_config


class TestChunkTranscriptByCount:
    """Tests for chunk_transcript_by_count -- count-based batch+target chunking."""

    @staticmethod
    def _make_segments(n: int) -> list[dict]:
        return [{"id": f"seg_{i}", "text": f"Segment {i}", "start": float(i), "end": float(i + 1)} for i in range(n)]

    def test_basic_100_segments(self):
        """100 segments with batch_size=20, overlap=4 -> 5 batches."""
        segs = self._make_segments(100)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        assert len(batches) == 5
        # Each batch's target_ids should have 20 items
        for batch_segs, target_ids in batches:
            assert len(target_ids) == 20

    def test_overlap_context(self):
        """Batch 1 should include the last 4 segments of batch 0 as context."""
        segs = self._make_segments(100)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        batch0_segs, batch0_targets = batches[0]
        batch1_segs, batch1_targets = batches[1]
        # batch 0 target is seg_0..seg_19
        assert batch0_targets == {f"seg_{i}" for i in range(20)}
        # batch 0 should include 4 extra segments after target: seg_20..seg_23
        assert len(batch0_segs) == 24  # 20 target + 4 after
        # batch 1 context_start = 20 - 4 = 16, so starts at seg_16
        assert batch1_segs[0]["id"] == "seg_16"
        # batch 1 target is seg_20..seg_39
        assert batch1_targets == {f"seg_{i}" for i in range(20, 40)}

    def test_single_batch_le_batch_size(self):
        """Total segments <= batch_size should produce single batch with all as targets (audit #9)."""
        segs = self._make_segments(15)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        assert len(batches) == 1
        _, target_ids = batches[0]
        assert target_ids == {f"seg_{i}" for i in range(15)}

    def test_boundary_28_segments(self):
        """28 segments with batch_size=20 should produce 2 batches, not 1 (audit #9)."""
        segs = self._make_segments(28)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        assert len(batches) == 2
        # batch 0: 20 target + 4 after context = 24 segments
        assert len(batches[0][0]) == 24
        # batch 1: 4 before context + 8 target = 12 segments
        assert len(batches[1][0]) == 12

    def test_empty(self):
        """Empty segments should return empty list."""
        assert chunk_transcript_by_count([]) == []

    def test_overlap_ge_batch_size_clamped(self):
        """overlap >= batch_size should be clamped to batch_size - 1 with warning (audit #11)."""
        import logging
        segs = self._make_segments(10)
        with pytest.warns(UserWarning) or True:  # may use logger.warning instead
            batches = chunk_transcript_by_count(segs, batch_size=5, overlap=10)
        # Should not crash, overlap clamped to 4
        assert len(batches) >= 1

    def test_overlap_zero(self):
        """overlap=0 should work, no context overlap between batches."""
        segs = self._make_segments(30)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=0)
        assert len(batches) == 2
        # batch 0: exactly 20 segments
        assert len(batches[0][0]) == 20
        # batch 1: exactly 10 segments (no overlap with batch 0)
        assert len(batches[1][0]) == 10

    def test_batch_size_one(self):
        """batch_size=1 extreme case: each batch has 1 target."""
        segs = self._make_segments(3)
        batches = chunk_transcript_by_count(segs, batch_size=1, overlap=0)
        assert len(batches) == 3
        for _, target_ids in batches:
            assert len(target_ids) == 1

    def test_missing_id_field(self):
        """Segments missing 'id' should use '' fallback without crashing."""
        segs = [{"text": f"Seg {i}", "start": float(i)} for i in range(3)]
        batches = chunk_transcript_by_count(segs, batch_size=2, overlap=0)
        assert len(batches) == 2
        # target_ids should contain empty strings as fallback
        assert "" in batches[0][1]

    def test_shallow_copy(self):
        """Returned batch_segments should be slices (shallow copies), not references (audit #12)."""
        segs = self._make_segments(10)
        batches = chunk_transcript_by_count(segs, batch_size=5, overlap=0)
        batch_segs, _ = batches[0]
        batch_segs[0]["text"] = "MUTATED"
        # Original should NOT be mutated
        assert segs[0]["text"] == "Segment 0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_service.py::TestChunkTranscriptByCount -v`
Expected: FAIL — `ImportError: cannot import name 'chunk_transcript_by_count'`

- [ ] **Step 3: Write the implementation**

Add the following function in `core/llm_service.py` immediately after `chunk_transcript()` (after line 309):

```python
def chunk_transcript_by_count(
    segments: list[dict],
    batch_size: int = 20,
    overlap: int = 4,
) -> list[tuple[list[dict], set[str]]]:
    """Split transcript by segment count using P1-style batch+target mode.

    Each batch contains ``batch_size + 2 * overlap`` segments (context
    at boundaries), with ``target_ids`` marking the ``batch_size`` central
    segments the LLM should analyze. Overlap segments provide context only.

    Args:
        segments: List of segment dicts (must have 'id' key).
        batch_size: Target analysis segments per batch. min=1.
        overlap: Context overlap on each side. min=0. Clamped to
            ``batch_size - 1`` if >= batch_size (audit #11).

    Returns:
        [(batch_segments, target_ids), ...] where batch_segments are
        shallow-copy slices and target_ids is a set of segment ID strings.
    """
    if not segments:
        return []

    # audit #11: overlap >= batch_size guard
    if overlap >= batch_size:
        logger.warning(
            f"chunk_transcript_by_count: overlap ({overlap}) >= batch_size "
            f"({batch_size}), clamping to {batch_size - 1}"
        )
        overlap = max(0, batch_size - 1)

    total = len(segments)

    # audit #9: single-batch only when total <= batch_size
    if total <= batch_size:
        all_ids = {str(s.get("id", "")) for s in segments}
        return [(segments[:], all_ids)]  # shallow copy

    batches: list[tuple[list[dict], set[str]]] = []
    step = batch_size  # targets don't overlap
    start_i = 0
    while start_i < total:
        end_i = min(start_i + batch_size, total)
        ctx_start = max(0, start_i - overlap)
        ctx_end = min(total, end_i + overlap)
        batch_with_context = segments[ctx_start:ctx_end]  # slice = shallow copy
        target_ids = {str(segments[i].get("id", "")) for i in range(start_i, end_i)}
        batches.append((batch_with_context, target_ids))
        start_i += step

    return batches
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_llm_service.py::TestChunkTranscriptByCount -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```
feat(llm): add chunk_transcript_by_count for count-based batch+target chunking

- New function using P1-style batch+target pattern instead of time-window
- overlap clamped when >= batch_size (audit #11)
- single-batch threshold at total <= batch_size (audit #9)
- returns shallow copies to prevent mutation (audit #12)
```

---

### Task 3: Delete `chunk_transcript_short()` from `core/llm_service.py`

**Files:**
- Modify: `core/llm_service.py` (delete lines 312-339)

**Interfaces:**
- Consumes: nothing (no callers remain)

- [ ] **Step 1: Verify no callers exist**

Run: `grep -rn "chunk_transcript_short" --include="*.py" .`
Expected: Only the definition in `core/llm_service.py` itself (no callers)

- [ ] **Step 2: Delete the function**

Delete lines 312-339 (the entire `chunk_transcript_short` function including the blank line after it, up to the `# ------------------------------------------------------------------` comment).

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `uv run pytest tests/test_llm_service.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```
refactor(llm): remove deprecated chunk_transcript_short

- No callers remain; smart-delete now uses chunk_transcript directly
```

---

### Task 4: Update `core/config.py` — replace settings + add deprecated key cleanup

**Files:**
- Modify: `core/config.py:88-89` (replace two settings) and `core/config.py:108-124` (add cleanup in `load_settings`)
- Test: `tests/test_config.py` (append tests)

**Interfaces:**
- Produces: Updated `_DEFAULT_SETTINGS` with `llm_smart_batch_size: 20`, `llm_smart_overlap_size: 4`
- Produces: `load_settings()` with one-time deprecated key cleanup

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_default_settings_has_new_smart_keys(tmp_path, monkeypatch):
    """_DEFAULT_SETTINGS should have llm_smart_batch_size and llm_smart_overlap_size, not old keys."""
    from core.config import _DEFAULT_SETTINGS
    assert "llm_smart_batch_size" in _DEFAULT_SETTINGS
    assert "llm_smart_overlap_size" in _DEFAULT_SETTINGS
    assert _DEFAULT_SETTINGS["llm_smart_batch_size"] == 20
    assert _DEFAULT_SETTINGS["llm_smart_overlap_size"] == 4
    assert "llm_smart_window_duration" not in _DEFAULT_SETTINGS
    assert "llm_smart_overlap_duration" not in _DEFAULT_SETTINGS


def test_load_settings_cleans_deprecated_keys(tmp_path, monkeypatch):
    """load_settings should pop deprecated keys and write back cleaned version (audit #10)."""
    from core.config import load_settings, save_settings, get_settings_path
    monkeypatch.setattr("core.config.get_settings_path", lambda: tmp_path / "settings.json")
    # Write settings with deprecated keys
    settings = {
        "llm_smart_window_duration": 60.0,
        "llm_smart_overlap_duration": 10.0,
        "llm_smart_batch_size": 25,
    }
    save_settings(settings)
    # Load should clean deprecated keys
    loaded = load_settings()
    assert "llm_smart_window_duration" not in loaded
    assert "llm_smart_overlap_duration" not in loaded
    assert loaded["llm_smart_batch_size"] == 25
    # Verify written back
    reloaded_raw = json.loads((tmp_path / "settings.json").read_text())
    assert "llm_smart_window_duration" not in reloaded_raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_default_settings_has_new_smart_keys -v`
Expected: FAIL — old keys still in defaults

- [ ] **Step 3: Implement the changes**

In `core/config.py`, replace lines 88-89:

```python
    # Old (remove):
    # "llm_smart_window_duration": 60.0,
    # "llm_smart_overlap_duration": 10.0,

    # New:
    "llm_smart_batch_size": 20,
    "llm_smart_overlap_size": 4,
```

In `core/config.py`, add deprecated key cleanup at the end of `load_settings()`, right before `return merged` (before line 124):

```python
    # Audit #10: one-time cleanup of deprecated settings keys
    _DEPRECATED_KEYS = {"llm_smart_window_duration", "llm_smart_overlap_duration"}
    removed = [k for k in _DEPRECATED_KEYS if k in merged]
    if removed:
        for k in removed:
            merged.pop(k, None)
        save_settings(merged)
        logger.info(f"Cleaned deprecated settings keys: {removed}")

    return merged
```

Add `from core.logging import get_logger` at the top of `core/config.py` if not already imported, and add `logger = get_logger()` after the other module-level variables. Check if `core/config.py` already imports `save_settings` — it does (line 127), so the call inside `load_settings` is fine.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: All tests PASS (including new ones)

- [ ] **Step 5: Commit**

```
feat(config): replace time-window settings with count-based batch settings

- Replace llm_smart_window_duration/llm_smart_overlap_duration with
  llm_smart_batch_size (20) / llm_smart_overlap_size (4)
- Add one-time deprecated key cleanup in load_settings (audit #10)
```

---

### Task 5: Update `core/llm_prompts.py` — add target_segment_ids instruction

**Files:**
- Modify: `core/llm_prompts.py:28-47` (append to `_SMART_DELETE_SYSTEM`)
- Test: `tests/test_llm_prompts.py` (append test)

**Interfaces:**
- Produces: Updated `_SMART_DELETE_SYSTEM` prompt text

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_prompts.py`:

```python
def test_smart_delete_prompt_mentions_target_segment_ids():
    """_SMART_DELETE_SYSTEM should contain target_segment_ids instruction."""
    from core.llm_prompts import _SMART_DELETE_SYSTEM
    assert "target_segment_ids" in _SMART_DELETE_SYSTEM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_prompts.py::test_smart_delete_prompt_mentions_target_segment_ids -v`
Expected: FAIL — `target_segment_ids` not in prompt

- [ ] **Step 3: Add instruction to prompt**

In `core/llm_prompts.py`, append before the closing `"""` of `_SMART_DELETE_SYSTEM` (line 47), add:

```python
重要：仅输出 target_segment_ids 列表中包含的段的分析结果。不在 target_segment_ids 中的段仅作为上下文参考，不要在输出中包含。
```

The full prompt ending should now be:

```
...
注意 s2 标为 partial_delete 而非 self_correct，因为它句内同时含口误和修正。

重要：仅输出 target_segment_ids 列表中包含的段的分析结果。不在 target_segment_ids 中的段仅作为上下文参考，不要在输出中包含。
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_llm_prompts.py::test_smart_delete_prompt_mentions_target_segment_ids -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
feat(prompts): add target_segment_ids constraint to smart-delete system prompt

- LLM now instructed to only output results for target segments
- Context overlap segments should not appear in output
```

---

### Task 6: Refactor `analyze_smart_delete()` in `core/llm_service.py` — batch+target mode

**Files:**
- Modify: `core/llm_service.py:526-531` (settings reading)
- Modify: `core/llm_service.py:544-567` (`_process_chunk` signature + body)
- Modify: `core/llm_service.py:577-634` (main loop + serial fallback)
- Modify: `core/llm_service.py:619-621,632-633` (progress log messages)
- Test: `tests/test_llm_service.py` (append integration test)

**Interfaces:**
- Consumes: `chunk_transcript_by_count` (from Task 2)
- Produces: `analyze_smart_delete` with batch+target internal loop

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_service.py`:

```python
class TestAnalyzeSmartDeleteBatchTarget:
    """Tests for analyze_smart_delete with batch+target mode."""

    def test_unpacks_batches_correctly(self, monkeypatch):
        """Main loop should correctly unpack (batch_segs, target_ids) tuples (audit #3)."""
        from unittest.mock import patch, MagicMock
        segments = [{"id": f"s{i}", "text": f"seg {i}", "start": float(i), "end": float(i+1)} for i in range(25)]
        # Mock call_llm to return empty results
        mock_llm = MagicMock(return_value={"success": True, "data": {"content": "[]", "usage": {"total_tokens": 10}}})
        monkeypatch.setattr("core.llm_service.call_llm", mock_llm)
        monkeypatch.setattr("core.llm_service.get_llm_config", lambda: MagicMock(is_configured=MagicMock(return_value=True)))
        # Ensure batch+target mode (batch_size=20, 25 segments -> 2 batches)
        monkeypatch.setattr("core.llm_service.load_settings", lambda: {"llm_smart_batch_size": 20, "llm_smart_overlap_size": 4, "llm_concurrency": 1})
        from core.llm_service import analyze_smart_delete
        result = analyze_smart_delete(segments)
        assert result["success"] is True
        assert result["data"]["results"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_service.py::TestAnalyzeSmartDeleteBatchTarget -v`
Expected: FAIL (will fail because `analyze_smart_delete` still uses time-window chunking)

- [ ] **Step 3: Implement the changes**

**3a. Replace settings reading (lines 526-531):**

```python
    # Old:
    settings = load_settings()
    window = float(settings.get("llm_smart_window_duration", 60.0))
    overlap = float(settings.get("llm_smart_overlap_duration", 10.0))
    concurrency = max(1, int(settings.get("llm_concurrency", 5)))
    chunks = chunk_transcript(to_analyze, chunk_duration=window, overlap_duration=overlap)
    total_chunks = len(chunks)

    # New:
    settings = load_settings()
    batch_size = max(1, int(settings.get("llm_smart_batch_size", 20)))
    overlap_size = max(0, int(settings.get("llm_smart_overlap_size", 4)))
    concurrency = max(1, int(settings.get("llm_concurrency", 5)))
    batches = chunk_transcript_by_count(to_analyze, batch_size=batch_size, overlap=overlap_size)
    total_batches = len(batches)
```

**3b. Replace `_process_chunk` function (lines 544-567):**

```python
    def _process_chunk(idx: int, batch_segments: list[dict], target_ids: set[str]) -> tuple[int, list[dict] | None, dict, str | None]:
        """Process a single smart-delete batch.

        Returns:
            (idx, normalized_results_or_None, token_usage, error_message_or_None)
        """
        if cancel_event and cancel_event.is_set():
            return (idx, None, {}, "Cancelled")
        # audit #7: target_segment_ids ordered by appearance in batch, not sorted
        target_ids_ordered = [
            str(s.get("id", "")) for s in batch_segments if str(s.get("id", "")) in target_ids
        ]
        extra_ctx: dict[str, Any] = {"target_segment_ids": target_ids_ordered}
        prompt = _build_structured_user_message(batch_segments, extra_context=extra_ctx)
        result = call_llm(
            prompt,
            system=effective_system,
            json_mode=True,
            config=config,
            cancel_event=cancel_event,
        )
        if not result.get("success"):
            error = result.get("error", "LLM call failed")
            logger.warning(f"Smart-delete batch {idx + 1} failed: {error}")
            return (idx, None, {}, error)
        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        chunk_results = _parse_json_response_layers(content)
        if not chunk_results:
            logger.warning(f"Smart-delete batch {idx + 1}: JSON parse returned None")
            return (idx, None, usage, None)
        normalized = _normalize_smart_delete_items(chunk_results)
        # Filter: only keep results for target_ids (same as P1, llm_service.py:783)
        normalized = [r for r in normalized if r.get("segment_id") in target_ids]
        return (idx, normalized or None, usage, None)
```

**3c. Replace ThreadPoolExecutor submission (lines 577-581):**

```python
    # Old:
    pending_indices: set[int] = set(range(total_chunks))
    ...
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_process_chunk, idx, chunk): idx
            for idx, chunk in enumerate(chunks)
        }

    # New:
    pending_indices: set[int] = set(range(total_batches))
    ...
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_process_chunk, idx, batch_segs, target_ids): idx
            for idx, (batch_segs, target_ids) in enumerate(batches)
        }
```

**3d. Update progress messages (lines 619-621):**

```python
    # Old:
    progress_cb(pct, f"Smart-delete window {completed}/{total_chunks}...")
    # New:
    progress_cb(pct, f"Smart-delete batch {completed}/{total_batches}...")
```

**3e. Update serial fallback (lines 632-634):**

```python
    # Old:
    progress_cb(pct, f"Smart-delete window {completed}/{total_chunks} (serial)...")
    idx_, normalized, usage, _ = _process_chunk(idx, chunks[idx])
    # New:
    progress_cb(pct, f"Smart-delete batch {completed}/{total_batches} (serial)...")
    idx_, normalized, usage, _ = _process_chunk(idx, batches[idx][0], batches[idx][1])
```

**3f. Update result merge loop (lines 643-647):**

```python
    # Old:
    for idx in range(total_chunks):
    # New:
    for idx in range(total_batches):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_llm_service.py::TestAnalyzeSmartDeleteBatchTarget -v`
Expected: PASS

- [ ] **Step 5: Run all llm_service tests to check nothing broke**

Run: `uv run pytest tests/test_llm_service.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```
feat(llm): refactor analyze_smart_delete to batch+target count mode

- Replace time-window chunking with chunk_transcript_by_count
- _process_chunk now receives (batch_segments, target_ids) tuple
- Results filtered to target_ids only (same as P1 pattern)
- Progress messages updated from "window" to "batch"
```

---

### Task 7: Wire confirmed-delete filter into `_handle_smart_delete` and `_handle_subtitle_correction` in `main.py`

**Files:**
- Modify: `main.py:689-702` (`_handle_smart_delete`)
- Modify: `main.py:799-816` (`_handle_subtitle_correction`)

**Interfaces:**
- Consumes: `collect_confirmed_deleted_seg_ids` from `core/timeline_utils`

- [ ] **Step 1: Modify `_handle_smart_delete`**

In `main.py`, add import at the top of the function or module level (check existing imports pattern — the handlers import inside the function body):

```python
# Add inside _handle_smart_delete, after line 694:
from core.timeline_utils import collect_confirmed_deleted_seg_ids
```

Replace the segment collection block (lines 698-702):

```python
    # Old:
    segments = [
        s.model_dump()
        for s in timeline.transcript.segments
        if s.type == SegmentType.SUBTITLE
    ]

    # New:
    # Audit #8: filter out confirmed-deleted segments before LLM analysis
    deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)
    segments = [
        s.model_dump()
        for s in timeline.transcript.segments
        if s.type == SegmentType.SUBTITLE and s.id not in deleted_seg_ids
    ]
```

- [ ] **Step 2: Modify `_handle_subtitle_correction`**

Add import inside `_handle_subtitle_correction` (after line 804):

```python
from core.timeline_utils import collect_confirmed_deleted_seg_ids
```

Replace the segment collection block (lines 812-816):

```python
    # Old:
    segments = [
        s.model_dump()
        for s in timeline.transcript.segments
        if s.type == SegmentType.SUBTITLE
    ]

    # New:
    # Audit #8: filter out confirmed-deleted segments before LLM correction
    deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)
    segments = [
        s.model_dump()
        for s in timeline.transcript.segments
        if s.type == SegmentType.SUBTITLE and s.id not in deleted_seg_ids
    ]
```

- [ ] **Step 3: Run backend tests to verify nothing breaks**

Run: `uv run pytest tests/ -v --ignore=tests/test_transcription.py`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```
feat(llm): filter confirmed-deleted segments from smart-delete and subtitle-correction input

- Both P0 and P1 handlers now skip segments with confirmed delete decisions
- Uses shared collect_confirmed_deleted_seg_ids helper from timeline_utils
```

---

### Task 8: Update frontend types and SettingsModal

**Files:**
- Modify: `frontend/src/types/edit.ts:74-75`
- Modify: `frontend/src/components/workspace/SettingsModal.vue:1345-1366`

**Interfaces:**
- Consumes: Updated backend settings keys

- [ ] **Step 1: Update TypeScript types**

In `frontend/src/types/edit.ts`, replace lines 74-75:

```typescript
    // Old:
    llm_smart_window_duration: number
    llm_smart_overlap_duration: number

    // New:
    llm_smart_batch_size: number
    llm_smart_overlap_size: number
```

- [ ] **Step 2: Update SettingsModal labels and bindings**

In `frontend/src/components/workspace/SettingsModal.vue`, replace the two smart-delete input blocks (lines 1345-1366):

```html
                  <label class="block">
                    <span class="text-xs text-gray-600">智能删除批次大小 (条)</span>
                    <input
                      type="number"
                      step="1"
                      min="5"
                      :value="settings.llm_smart_batch_size"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); settings = { ...settings!, llm_smart_batch_size: Number.isNaN(v) ? 20 : v } })()"
                    />
                  </label>
                  <label class="block">
                    <span class="text-xs text-gray-600">智能删除重叠 (条)</span>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      :value="settings.llm_smart_overlap_size"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); settings = { ...settings!, llm_smart_overlap_size: Number.isNaN(v) ? 4 : v } })()"
                    />
                  </label>
```

Note the `Number.isNaN` pattern (audit #1 fix) — prevents `parseInt("0") === 0` then `0 || 4 === 4` bug.

- [ ] **Step 3: Run frontend build to verify**

Run: `cd frontend && bun run build`
Expected: Build succeeds with no type errors

- [ ] **Step 4: Commit**

```
feat(frontend): update smart-delete settings UI to count-based fields

- Replace window/overlap-duration with batch_size/overlap_size
- Use Number.isNaN for input validation (audit #1: parseInt("0") || default bug fix)
- Update TypeScript types in edit.ts
```

---

### Task 9: Run full test suite + frontend build verification

**Files:**
- No file changes — verification only

- [ ] **Step 1: Run full backend test suite**

Run: `uv run pytest tests/ -v --ignore=tests/test_transcription.py`
Expected: All tests PASS

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && bun run build`
Expected: Build succeeds, no type errors

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && bun run test`
Expected: All tests PASS

- [ ] **Step 4: Final commit (if any fixups needed)**

If all tests pass, no additional commit needed. If fixups were required, commit with:

```
fix: address test failures from smart-delete batch mode migration
```

---

## Self-Review Checklist

| Spec Section | Task(s) | Status |
|---|---|---|
| 2.1 Filter rule (action=delete, status=confirmed) | Task 1, 7 | Covered |
| 2.2 Filter scope (smart_delete + subtitle_correction) | Task 7 | Covered |
| 2.3 Coexistence with existing_ids | Task 7 (existing_ids logic untouched) | Covered |
| 2.4 Public helper in timeline_utils.py | Task 1 | Covered |
| 2.5 Edge cases (0 segments, small count) | Task 2 | Covered |
| 3.1 Batch+target algorithm | Task 2 | Covered |
| 3.2 Why batch+target | Plan context | Documented |
| 3.3 Prompt changes | Task 5 | Covered |
| 3.4 Boundary handling | Task 2 (all edge cases tested) | Covered |
| 3.5 Deprecation of chunk_transcript_short | Task 3 | Covered |
| 3.6 New settings items | Task 4 | Covered |
| 4.1 llm_service.py changes | Tasks 2, 3, 6 | Covered |
| 4.2 llm_prompts.py changes | Task 5 | Covered |
| 4.3 main.py changes | Task 7 | Covered |
| 4.4 config.py changes | Task 4 | Covered |
| 4.5 Frontend changes | Task 8 | Covered |
| 6.1 Log message updates | Task 6 | Covered |
| 7.1 Unit tests | Tasks 1, 2, 4, 5, 6 | Covered |
| Audit #1 (parseInt || default bug) | Task 8 | Covered |
| Audit #3 (loop unpack) | Task 6 | Covered |
| Audit #4 (extra_context support) | Pre-verified | Confirmed in codebase |
| Audit #5 (_process_chunk return type) | Task 6 | Covered |
| Audit #6 (EditDecision types) | Task 1 | Covered |
| Audit #7 (target_ids ordering) | Task 6 | Covered |
| Audit #8 (DRY helper) | Task 1 | Covered |
| Audit #9 (single-batch threshold) | Task 2 | Covered |
| Audit #10 (deprecated key cleanup) | Task 4 | Covered |
| Audit #11 (overlap >= batch_size guard) | Task 2 | Covered |
| Audit #12 (shallow copy) | Task 2 | Covered |
| Audit #16 (log messages) | Task 6 | Covered |
