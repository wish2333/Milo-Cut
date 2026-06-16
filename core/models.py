"""Pydantic v2 data models for Milo-Cut.

All models are frozen (immutable) by default.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ================================================================
# Enums / Literal types
# ================================================================


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    # MVP
    SILENCE_DETECTION = "silence_detection"
    EXPORT_VIDEO = "export_video"
    EXPORT_SUBTITLE = "export_subtitle"
    EXPORT_AUDIO = "export_audio"
    EXPORT_VTT = "export_vtt"
    # P1
    FILLER_DETECTION = "filler_detection"
    ERROR_DETECTION = "error_detection"
    FULL_ANALYSIS = "full_analysis"
    TRANSCRIPTION = "transcription"
    VAD_ANALYSIS = "vad_analysis"
    WAVEFORM_GENERATION = "waveform_generation"
    PLUGIN_INSTALL = "plugin_install"
    MODEL_DOWNLOAD = "model_download"
    PROXY_GENERATION = "proxy_generation"
    # LLM
    LLM_SMART_DELETE = "llm_smart_delete"
    LLM_SUBTITLE_CORRECTION = "llm_subtitle_correction"
    LLM_HIGHLIGHT = "llm_highlight"
    LLM_SEMANTIC_SEARCH = "llm_semantic_search"


class EditStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SegmentType(StrEnum):
    SUBTITLE = "subtitle"
    SILENCE = "silence"


# ================================================================
# Core data models
# ================================================================


class Word(BaseModel, frozen=True):
    word: str
    start: float
    end: float
    confidence: float = 1.0


class Segment(BaseModel, frozen=True):
    id: str
    version: int = 1
    type: SegmentType = SegmentType.SUBTITLE
    start: float
    end: float
    text: str = ""
    words: list[Word] = Field(default_factory=list)
    speaker: str = ""
    dirty_flags: dict[str, bool] = Field(default_factory=dict)


class MediaInfo(BaseModel, frozen=True):
    path: str
    media_hash: str = ""
    duration: float = 0.0
    format: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    pix_fmt: str = ""
    audio_channels: int = 0
    sample_rate: int = 0
    bit_rate: int = 0
    proxy_path: str | None = None
    waveform_path: str | None = None


class EditDecision(BaseModel, frozen=True):
    id: str
    start: float
    end: float
    action: Literal["delete", "keep"] = "delete"
    source: str = ""
    analysis_id: str | None = None
    status: EditStatus = EditStatus.PENDING
    priority: int = 100
    target_type: Literal["segment", "range"] = "range"
    target_id: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> EditDecision:
        if self.target_type == "segment" and self.target_id is None:
            raise ValueError('target_id is required when target_type is "segment"')
        return self


class TaskProgress(BaseModel, frozen=True):
    percent: float = 0.0
    message: str = ""


class MiloTask(BaseModel, frozen=True):
    id: str
    type: TaskType
    status: TaskStatus = TaskStatus.QUEUED
    progress: TaskProgress = Field(default_factory=TaskProgress)
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    completed_at: str | None = None


class ProjectMeta(BaseModel, frozen=True):
    name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class TranscriptData(BaseModel, frozen=True):
    engine: str = "srt"
    language: str = "zh-CN"
    segments: list[Segment] = Field(default_factory=list)


class AnalysisResult(BaseModel, frozen=True):
    id: str
    type: Literal["filler", "error", "duplicate", "punctuation",
                  "llm_smart_delete", "llm_subtitle_correction", "llm_highlight"]
    segment_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    detail: str = ""


# ================================================================
# Plugin / Model info
# ================================================================


class PluginInfo(BaseModel, frozen=True):
    """Information about an installed ASR plugin."""

    plugin_id: str
    display_name: str
    engine: Literal["faster-whisper", "qwen3-asr"]
    version: str = "1.0.0"
    status: Literal["installed", "installing", "not_installed", "error"] = "not_installed"
    installed_at: str = ""
    venv_path: str = ""


class ModelInfo(BaseModel, frozen=True):
    """Information about a downloaded ML model."""

    model_id: str
    display_name: str
    plugin_id: str
    size_bytes: int = 0
    local_path: str = ""
    status: Literal["downloaded", "downloading", "not_downloaded"] = "not_downloaded"


# ================================================================
# LLM configuration
# ================================================================


class LlmProvider(StrEnum):
    """Supported LLM API providers (all OpenAI-compatible)."""

    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    QWEN = "qwen"
    GLM = "glm"
    CUSTOM = "custom"


# Provider-specific defaults
# Ordered by recommended priority (DeepSeek first as default).
_PROVIDER_DEFAULTS: dict[LlmProvider, dict[str, str]] = {
    LlmProvider.DEEPSEEK: {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-flash",
    },
    LlmProvider.OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.4-mini",
    },
    LlmProvider.QWEN: {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    LlmProvider.GLM: {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5-turbo",
    },
    LlmProvider.CUSTOM: {
        "base_url": "",
        "model": "",
    },
}


class LlmConfig(BaseModel, frozen=True):
    """LLM provider configuration stored in settings."""

    provider: LlmProvider = LlmProvider.CUSTOM
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.3
    timeout: int = 120
    thinking_enabled: bool = False

    def resolved_base_url(self) -> str:
        """Return configured base_url or provider default."""
        if self.base_url:
            return self.base_url
        return _PROVIDER_DEFAULTS.get(self.provider, {}).get("base_url", "")

    def resolved_model(self) -> str:
        """Return configured model or provider default."""
        if self.model:
            return self.model
        return _PROVIDER_DEFAULTS.get(self.provider, {}).get("model", "")

    def is_configured(self) -> bool:
        """Check if the minimum required fields are set."""
        return bool(self.resolved_base_url() and self.api_key and self.resolved_model())

    @property
    def supports_thinking(self) -> bool:
        """Check if this provider supports thinking mode.

        DeepSeek: yes (deepseek-v4-flash and above).
        OpenAI: no (GPT models don't support thinking).
        Qwen: yes (qwen-plus and above, via extra_body).
        GLM: yes (glm-5 and above, via extra_body).
        Custom: unknown -- default to True if base_url is non-empty.
        """
        if self.provider == LlmProvider.OPENAI:
            return False
        if self.provider == LlmProvider.CUSTOM:
            return bool(self.resolved_base_url())
        return True

    def thinking_extra_body(self) -> dict | None:
        """Return extra_body dict for thinking mode, or None if disabled.

        Most OpenAI-compatible APIs (DeepSeek, Qwen, GLM) accept the
        ``{"thinking": {"type": "enabled"}}`` payload in extra_body.
        """
        if not self.thinking_enabled or not self.supports_thinking:
            return None
        return {"thinking": {"type": "enabled"}}


# ================================================================
# Analysis data + Timeline (multi-timeline infrastructure, v2.0.0)
# ================================================================


class AnalysisData(BaseModel, frozen=True):
    last_run: str | None = None
    results: list[AnalysisResult] = Field(default_factory=list)


class Timeline(BaseModel, frozen=True):
    """Independent timeline -- owns a complete transcript + edits + analysis.

    Each Timeline is a self-contained (transcript, edits, analysis) triple.
    Switching timelines does not affect others. LLM operations run on forked
    timelines so the original is never mutated.
    """

    id: str  # unique identifier ("default" / "subtitle-fix-v1" / "smart-delete-v2")
    label: str  # user-visible name
    source: str = "manual"  # creation source ("manual" / "fork" / "llm_p0" / "llm_p1" / "migrated")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    parent_id: str = ""  # fork origin (empty = root timeline)
    transcript: TranscriptData = Field(default_factory=TranscriptData)
    edits: list[EditDecision] = Field(default_factory=list)
    analysis: AnalysisData = Field(default_factory=AnalysisData)
    # Phase 3: Project-level LLM prompt overrides (per-timeline).
    # Structure: {"smart_delete": {"system_override": str, "params": {...}}}
    # Empty dict = use global settings prompts.
    llm_prompts: dict = Field(default_factory=dict)


# ================================================================
# Project (v2 multi-timeline schema)
# ================================================================


class Project(BaseModel, frozen=True):
    # Allow mutation of _internal fields despite frozen=True (for ProjectService)
    model_config = {"frozen": True}

    schema_version: int = 2
    project: ProjectMeta = Field(default_factory=ProjectMeta)
    media: MediaInfo | None = None

    # Multi-timeline container (v2 schema)
    timelines: list[Timeline] = Field(default_factory=list)
    active_timeline_id: str = "default"

    # Backward-compat: v1 flat fields kept for migration reading.
    # After _migrate_to_v2 these are never populated on new projects.
    # They default to empty and are excluded from dumps when timelines is set.

    @model_validator(mode="after")
    def ensure_default_timeline(self) -> Project:
        """Ensure at least one timeline exists and active_timeline_id is valid."""
        if not self.timelines:
            # Create empty default timeline if none exists
            default = Timeline(id="default", label="原始", source="default")
            object.__setattr__(self, "timelines", [default])
        ids = {tl.id for tl in self.timelines}
        if self.active_timeline_id not in ids:
            object.__setattr__(self, "active_timeline_id", self.timelines[0].id)
        return self

    def get_timeline(self, timeline_id: str) -> Timeline | None:
        """Get a timeline by ID, or None if not found."""
        for tl in self.timelines:
            if tl.id == timeline_id:
                return tl
        return None

    @property
    def active_timeline(self) -> Timeline:
        """The currently active timeline."""
        tl = self.get_timeline(self.active_timeline_id)
        if tl is None:
            # Fallback to first timeline (shouldn't happen due to validator)
            return self.timelines[0]
        return tl
