"""Tests for the translation prompt registration (v3.0.4 M1-3, PLAN P1-2).

SPEC M1-3 key ruling: ``DEFAULT_PROMPTS["translation"]["params"]`` must stay
empty. ``_inject_placeholders`` only iterates registered param keys and
``_format_param`` returns "" for unregistered keys -- registering
``target_language`` in params would blank the placeholder and silently drop
the language. With params empty, ``{{target_language}}`` survives the full
``get_effective_prompt`` resolution (hardcoded default -> global settings ->
project timeline override) plus the ``system_override`` early-return path;
the handler performs the final ``.replace("{{target_language}}", ...)``
(P1-5, together with the residual ``{{`` fail-fast case -- PLAN micro-ruling).
"""

import re

from core.llm_prompts import (
    _TRANSLATION_SYSTEM,
    DEFAULT_PROMPTS,
    get_default_params,
    get_default_prompt_text,
    get_effective_prompt,
)


class TestTranslationRegistration:
    """Registry guards for the translation prompt entry."""

    def test_translation_key_registered(self):
        assert "translation" in DEFAULT_PROMPTS

    def test_registry_params_empty(self):
        # SPEC M1-3 key ruling (anti-regression guard): params must be {}.
        # This is what lets {{target_language}} pass through
        # _inject_placeholders untouched instead of being blanked.
        assert DEFAULT_PROMPTS["translation"]["params"] == {}

    def test_get_default_params_empty(self):
        assert get_default_params("translation") == {}

    def test_default_prompt_text_contains_placeholder(self):
        assert "{{target_language}}" in get_default_prompt_text("translation")

    def test_system_prompt_content_requirements(self):
        # SPEC M1-3: per-entry JSON array output, ids echoed back as-is,
        # no added or dropped entries, JSON array only.
        assert "target_segment_ids" in _TRANSLATION_SYSTEM
        assert "segment_id" in _TRANSLATION_SYSTEM
        assert "translated_text" in _TRANSLATION_SYSTEM
        assert "JSON array" in _TRANSLATION_SYSTEM
        assert "Do not add, drop, merge, or split entries" in _TRANSLATION_SYSTEM

    def test_target_language_is_the_only_placeholder(self):
        # Premise for the P1-5 handler fail-fast: after the final
        # {{target_language}} replace, no other {{...}} may remain.
        placeholders = re.findall(r"\{\{[^}]*\}\}", _TRANSLATION_SYSTEM)
        assert placeholders, "translation prompt must carry the placeholder"
        assert set(placeholders) == {"{{target_language}}"}


class TestPlaceholderPenetration:
    """{{target_language}} must survive every resolution layer."""

    def test_hardcoded_default_layer(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings", lambda: {"llm_prompts": {}}
        )
        result = get_effective_prompt("translation")
        assert "{{target_language}}" in result

    def test_hardcoded_default_layer_empty_settings(self, monkeypatch):
        monkeypatch.setattr("core.config.load_settings", lambda: {})
        result = get_effective_prompt("translation")
        assert "{{target_language}}" in result

    def test_hardcoded_default_layer_empty_project_prompts(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings", lambda: {"llm_prompts": {}}
        )
        result = get_effective_prompt("translation", {})
        assert "{{target_language}}" in result

    def test_global_settings_layer(self, monkeypatch):
        # A configured translation entry in settings llm_prompts runs the
        # params merge, but no registered key consumes the placeholder.
        monkeypatch.setattr(
            "core.config.load_settings",
            lambda: {
                "llm_prompts": {
                    "translation": {"params": {"glossary": ["K8s"]}}
                }
            },
        )
        result = get_effective_prompt("translation")
        assert "{{target_language}}" in result

    def test_project_override_layer(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings", lambda: {"llm_prompts": {}}
        )
        project_prompts = {
            "translation": {"params": {"glossary": ["K8s"]}}
        }
        result = get_effective_prompt("translation", project_prompts)
        assert "{{target_language}}" in result

    def test_system_override_path(self, monkeypatch):
        # Early-return path: system_override is returned verbatim and the
        # placeholder passes through untouched (final replace is P1-5's).
        monkeypatch.setattr(
            "core.config.load_settings", lambda: {"llm_prompts": {}}
        )
        project_prompts = {
            "translation": {
                "system_override": "Translate all segments to {{target_language}}."
            }
        }
        result = get_effective_prompt("translation", project_prompts)
        assert result == "Translate all segments to {{target_language}}."
        assert "{{target_language}}" in result

    def test_system_override_from_settings_layer(self, monkeypatch):
        monkeypatch.setattr(
            "core.config.load_settings",
            lambda: {
                "llm_prompts": {
                    "translation": {
                        "system_override": "Custom {{target_language}} prompt."
                    }
                }
            },
        )
        result = get_effective_prompt("translation")
        assert result == "Custom {{target_language}} prompt."
