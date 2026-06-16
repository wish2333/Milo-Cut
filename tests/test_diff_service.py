"""Tests for core.diff_service (v2.1.0 Phase 2).

Covers compute_inline_diff: Chinese character-level diff, identical inputs,
pure insert/delete/replace, empty inputs, and the batch helper.
"""

from __future__ import annotations

from core.diff_service import compute_diffs_batch, compute_inline_diff


class TestComputeInlineDiff:
    def test_identical_text_single_equal_token(self):
        result = compute_inline_diff("相同文本", "相同文本")
        assert result["tokens"] == [{"text": "相同文本", "type": "equal"}]

    def test_chinese_replace_emits_delete_then_insert(self):
        """D-56: Chinese char-level diff; replace -> delete + insert (D-69)."""
        result = compute_inline_diff("这是错字示例", "这是正字示例")
        types = [t["type"] for t in result["tokens"]]
        # "错" -> "正" is the only change
        assert "delete" in types and "insert" in types
        delete_tok = next(t for t in result["tokens"] if t["type"] == "delete")
        insert_tok = next(t for t in result["tokens"] if t["type"] == "insert")
        assert delete_tok["text"] == "错"
        assert insert_tok["text"] == "正"
        # Surrounding equal tokens preserved
        equals = [t["text"] for t in result["tokens"] if t["type"] == "equal"]
        assert "这是" in equals
        assert "字示例" in equals

    def test_pure_insert(self):
        result = compute_inline_diff("你好", "你好世界")
        types = [t["type"] for t in result["tokens"]]
        assert "insert" in types
        insert_tok = next(t for t in result["tokens"] if t["type"] == "insert")
        assert insert_tok["text"] == "世界"

    def test_pure_delete(self):
        result = compute_inline_diff("你好世界", "你好")
        types = [t["type"] for t in result["tokens"]]
        assert "delete" in types
        delete_tok = next(t for t in result["tokens"] if t["type"] == "delete")
        assert delete_tok["text"] == "世界"

    def test_english_diff(self):
        result = compute_inline_diff("hello world", "hello earth")
        # difflib finds the common "r" -> two delete/insert pairs.
        deletes = [t["text"] for t in result["tokens"] if t["type"] == "delete"]
        inserts = [t["text"] for t in result["tokens"] if t["type"] == "insert"]
        # "wo"+"ld" deleted, "ea"+"th" inserted (the changed regions)
        assert "wo" in deletes and "ld" in deletes
        assert "ea" in inserts and "th" in inserts

    def test_completely_different(self):
        result = compute_inline_diff("甲", "乙")
        # No common subsequence -> single replace (delete + insert)
        types = [t["type"] for t in result["tokens"]]
        assert types == ["delete", "insert"]

    def test_both_empty(self):
        result = compute_inline_diff("", "")
        assert result["tokens"] == []

    def test_original_empty(self):
        result = compute_inline_diff("", "新增")
        assert result["tokens"] == [{"text": "新增", "type": "insert"}]

    def test_corrected_empty(self):
        result = compute_inline_diff("删除", "")
        assert result["tokens"] == [{"text": "删除", "type": "delete"}]

    def test_tokens_have_text_and_type_only(self):
        """Tokens carry no backend-specific fields (frontend aggregation D-69)."""
        result = compute_inline_diff("ab", "ac")
        for tok in result["tokens"]:
            assert set(tok.keys()) == {"text", "type"}
            assert tok["type"] in ("equal", "delete", "insert")

    def test_whitespace_only_difference(self):
        result = compute_inline_diff("a b", "a  b")
        types = [t["type"] for t in result["tokens"]]
        # The extra space is an insert
        assert "insert" in types


class TestComputeDiffsBatch:
    def test_batch_preserves_order(self):
        pairs = [
            {"original": "甲", "corrected": "乙"},
            {"original": "相同", "corrected": "相同"},
            {"original": "hello", "corrected": "hi"},
        ]
        results = compute_diffs_batch(pairs)
        assert len(results) == 3
        # First: replace
        assert any(t["type"] == "delete" for t in results[0]["tokens"])
        # Second: identical
        assert results[1]["tokens"] == [{"text": "相同", "type": "equal"}]
        # Third: has diff
        assert results[2]["tokens"] != []

    def test_empty_batch(self):
        assert compute_diffs_batch([]) == []

    def test_missing_keys_default_to_empty(self):
        results = compute_diffs_batch([{}])
        assert results == [{"tokens": []}]
