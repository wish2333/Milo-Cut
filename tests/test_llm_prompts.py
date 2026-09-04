"""Tests for core.llm_prompts module (Phase 3)."""


from core.llm_prompts import (
    DEFAULT_PROMPTS,
    _format_param,
    _inject_placeholders,
    get_default_params,
    get_default_prompt_text,
    get_effective_prompt,
)


class TestDefaultPrompts:
    """Verify the DEFAULT_PROMPTS registry structure."""

    EXPECTED_KEYS = {
        "smart_delete",
        "subtitle_correction_a",
        "subtitle_correction_b",
        "highlight",
        "search",
        "translation",  # v3.0.4 M1-3: translation prompt 注册
    }

    def test_all_expected_keys_present(self):
        assert set(DEFAULT_PROMPTS.keys()) == self.EXPECTED_KEYS

    def test_each_entry_has_system_and_params(self):
        for key, entry in DEFAULT_PROMPTS.items():
            assert "system" in entry, f"{key} missing 'system'"
            assert isinstance(entry["system"], str) and entry["system"]
            assert "params" in entry, f"{key} missing 'params'"
            assert isinstance(entry["params"], dict)

    def test_smart_delete_has_custom_fillers_placeholder(self):
        assert "{{custom_fillers}}" in DEFAULT_PROMPTS["smart_delete"]["system"]

    def test_subtitle_correction_a_has_glossary_placeholder(self):
        assert "{{glossary}}" in DEFAULT_PROMPTS["subtitle_correction_a"]["system"]

    def test_subtitle_correction_b_has_glossary_placeholder(self):
        assert "{{glossary}}" in DEFAULT_PROMPTS["subtitle_correction_b"]["system"]

    def test_highlight_has_focus_keywords_placeholder(self):
        assert "{{focus_keywords}}" in DEFAULT_PROMPTS["highlight"]["system"]

    def test_search_has_no_placeholders(self):
        system = DEFAULT_PROMPTS["search"]["system"]
        assert "{{" not in system, "search prompt should have no placeholders"


class TestFormatParam:
    """Test _format_param for each parameter type."""

    def test_empty_list_returns_empty_string(self):
        assert _format_param("custom_fillers", [], "smart_delete") == ""

    def test_whitespace_only_items_filtered(self):
        # Items with only spaces should be stripped and filtered out
        result = _format_param("custom_fillers", ["  ", ""], "smart_delete")
        assert result == ""

    def test_custom_fillers_format(self):
        result = _format_param("custom_fillers", ["那个", "就是说"], "smart_delete")
        assert "额外需要检测的口头禅" in result
        assert "那个" in result
        assert "就是说" in result

    def test_glossary_format(self):
        result = _format_param("glossary", ["K8s"], "subtitle_correction_a")
        assert "参考术语表" in result
        assert "K8s" in result

    def test_focus_keywords_format(self):
        result = _format_param("focus_keywords", ["性能"], "highlight")
        assert "特别关注这些关键词" in result
        assert "性能" in result

    def test_items_are_stripped(self):
        # Leading/trailing whitespace on individual items is removed
        result = _format_param("custom_fillers", ["  那个  "], "smart_delete")
        assert "那个" in result


class TestInjectPlaceholders:
    """Test _inject_placeholders for {{param}} replacement."""

    def test_placeholder_replaced_with_content(self):
        prompt = "Base\n{{custom_fillers}}\nEnd"
        result = _inject_placeholders(
            prompt, {"custom_fillers": ["那个"]}, "smart_delete"
        )
        assert "{{custom_fillers}}" not in result
        assert "额外需要检测的口头禅" in result

    def test_placeholder_replaced_with_empty_when_no_values(self):
        prompt = "Base\n{{custom_fillers}}\nEnd"
        result = _inject_placeholders(prompt, {"custom_fillers": []}, "smart_delete")
        assert "{{custom_fillers}}" not in result
        # Empty replacement -- placeholder is replaced with ""
        assert result == "Base\n\nEnd"

    def test_missing_placeholder_in_prompt_skipped(self):
        prompt = "No placeholder here"
        result = _inject_placeholders(
            prompt, {"custom_fillers": ["那个"]}, "smart_delete"
        )
        assert result == prompt  # Unchanged


class TestGetEffectivePrompt:
    """Test get_effective_prompt layered resolution."""

    def test_returns_default_when_no_overrides(self, monkeypatch):
        # Patch load_settings to return empty llm_prompts

        monkeypatch.setattr(
            "core.config.load_settings", lambda: {"llm_prompts": {}}
        )
        result = get_effective_prompt("smart_delete")
        # Should contain the default system prompt with placeholder resolved
        assert "清理助手" in result
        assert "{{custom_fillers}}" not in result

    def test_global_params_injected(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings",
            lambda: {
                "llm_prompts": {
                    "smart_delete": {"params": {"custom_fillers": ["那个"]}}
                }
            },
        )
        result = get_effective_prompt("smart_delete")
        assert "额外需要检测的口头禅" in result
        assert "那个" in result

    def test_system_override_takes_priority(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings",
            lambda: {
                "llm_prompts": {
                    "smart_delete": {
                        "system_override": "CUSTOM PROMPT TEXT",
                        "params": {"custom_fillers": ["那个"]},
                    }
                }
            },
        )
        result = get_effective_prompt("smart_delete")
        assert result == "CUSTOM PROMPT TEXT"

    def test_project_overrides_priority_over_global(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings",
            lambda: {
                "llm_prompts": {
                    "smart_delete": {"params": {"custom_fillers": ["global"]}}
                }
            },
        )
        project_prompts = {
            "smart_delete": {"params": {"custom_fillers": ["project"]}}
        }
        result = get_effective_prompt("smart_delete", project_prompts)
        assert "project" in result
        assert "global" not in result

    def test_empty_system_override_falls_through_to_simple_mode(self, monkeypatch):
        # Empty/whitespace system_override should NOT be used
        monkeypatch.setattr(
            "core.config.load_settings",
            lambda: {
                "llm_prompts": {
                    "smart_delete": {
                        "system_override": "   ",
                        "params": {"custom_fillers": ["那个"]},
                    }
                }
            },
        )
        result = get_effective_prompt("smart_delete")
        assert "清理助手" in result  # Default prompt used
        assert "那个" in result  # Params still injected

    def test_unknown_key_returns_empty(self, monkeypatch):
        monkeypatch.setattr("core.config.load_settings", lambda: {})
        result = get_effective_prompt("nonexistent_key")
        assert result == ""

    def test_search_returns_prompt_without_modification(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings", lambda: {"llm_prompts": {}}
        )
        result = get_effective_prompt("search")
        assert "内容检索助手" in result


class TestHelperFunctions:
    """Test get_default_prompt_text and get_default_params."""

    def test_get_default_prompt_text(self):
        text = get_default_prompt_text("smart_delete")
        assert "清理助手" in text
        assert "{{custom_fillers}}" in text  # Contains placeholder

    def test_get_default_prompt_text_unknown_key(self):
        assert get_default_prompt_text("nonexistent") == ""

    def test_get_default_params(self):
        params = get_default_params("smart_delete")
        assert "custom_fillers" in params
        assert params["custom_fillers"] == []

    def test_get_default_params_search_empty(self):
        params = get_default_params("search")
        assert params == {}

    def test_get_default_params_unknown_key(self):
        assert get_default_params("nonexistent") == {}


def test_smart_delete_prompt_mentions_target_segment_ids():
    """_SMART_DELETE_SYSTEM should contain target_segment_ids instruction."""
    from core.llm_prompts import _SMART_DELETE_SYSTEM
    assert "target_segment_ids" in _SMART_DELETE_SYSTEM
    assert "仅输出 target_segment_ids 列表中包含的段的分析结果" in _SMART_DELETE_SYSTEM
    assert "不在 target_segment_ids 中的段仅作为上下文参考" in _SMART_DELETE_SYSTEM
