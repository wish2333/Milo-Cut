"""Pydantic v2 data models for Milo-Cut.

All models are frozen (immutable) by default.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


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
    # P1
    FILLER_DETECTION = "filler_detection"
    ERROR_DETECTION = "error_detection"
    FULL_ANALYSIS = "full_analysis"
    TRANSCRIPTION = "transcription"
    VAD_ANALYSIS = "vad_analysis"
    WAVEFORM_GENERATION = "waveform_generation"


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
    type: Literal["filler", "error"]
    segment_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    detail: str = ""


class AnalysisData(BaseModel, frozen=True):
    last_run: str | None = None
    results: list[AnalysisResult] = Field(default_factory=list)


class Project(BaseModel, frozen=True):
    schema_version: int = 1
    project: ProjectMeta = Field(default_factory=ProjectMeta)
    media: MediaInfo | None = None
    transcript: TranscriptData = Field(default_factory=TranscriptData)
    analysis: AnalysisData = Field(default_factory=AnalysisData)
    edits: list[EditDecision] = Field(default_factory=list)
