"""Synthetic project generator for v2.3.2 performance baselines.

Generates a deterministic synthetic :class:`Project` that mirrors the shape
of a real long-form oral-presentation recording, as referenced in
``docs/2.3.0/2.3.2-fix-report.md`` §6.3 (no in-repo fixture exists).

Design goals
------------
1. **Deterministic** -- same ``seed`` always produces byte-identical output,
   so consecutive benchmark runs are comparable.
2. **Realistic distribution** -- 80% subtitle / 20% silence segments; edits
   drawn from the actual sources used in production (``manual`` /
   ``silence_detection`` / ``llm_smart_delete``); realistic text lengths.
3. **Configurable** -- size scales via ``segment_count`` / ``edit_count``
   while keeping the target distribution.
4. **No external IO** -- generation is pure; persistence (if needed) is the
   caller's responsibility.

CLI usage::

    uv run python -m tests.fixtures.generate_synthetic_project \\
        --output data/perf/synthetic_1167.json \\
        --segments 1167 --edits 989

Library usage::

    from tests.fixtures.generate_synthetic_project import (
        generate_synthetic_project,
    )
    project = generate_synthetic_project(segment_count=1167, edit_count=989)
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime
from pathlib import Path

from core.models import (
    EditDecision,
    EditStatus,
    MediaInfo,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    Timeline,
    TranscriptData,
)

# Default target size referenced by the v2.3.2 evaluation plan §4 阶段 0.
DEFAULT_SEGMENT_COUNT = 1167
DEFAULT_EDIT_COUNT = 989
DEFAULT_SEED = 42

# Fixed timestamp for full determinism -- ``datetime.now()`` defaults in
# core.models would otherwise make two consecutive runs differ.
DEFAULT_CREATED_AT = "2026-07-21T00:00:00"

# Distribution knobs (kept as module constants so they can be tuned without
# touching the generator signature).
SILENCE_RATIO = 0.20  # 20% of segments are silence gaps
SUBTITLE_DURATION_RANGE = (2.5, 8.5)  # seconds; realistic spoken-segment span
SILENCE_DURATION_RANGE = (0.4, 2.5)  # seconds
INTER_SEGMENT_GAP_RANGE = (0.05, 0.4)  # seconds

# Edit sources weighted to mirror a project after silence detection + a
# typical LLM smart-delete pass. Weights sum to 1.0.
EDIT_SOURCE_WEIGHTS = (
    ("silence_detection", 0.45),
    ("llm_smart_delete", 0.30),
    ("manual", 0.15),
    ("subtitle_correction", 0.10),
)

# Edit status distribution for confirmed/pending/rejected.
EDIT_STATUS_WEIGHTS = (
    (EditStatus.PENDING, 0.55),
    (EditStatus.CONFIRMED, 0.35),
    (EditStatus.REJECTED, 0.10),
)

# Sample Chinese text fragments -- intentionally generic to avoid any
# real-transcript leakage. Mixed lengths to exercise text-handling paths.
_SAMPLE_TEXTS = [
    "今天我们来谈一谈这个项目的整体进展情况",
    "首先需要明确的是我们在这一阶段所取得的关键成果",
    "在产品迭代的过程中遇到了一些挑战但都已经解决",
    "接下来我会详细介绍每一个核心指标的变化趋势",
    "需要特别强调的是用户反馈在我们决策中占据了重要位置",
    "从数据层面来看留存率和活跃度都呈现出稳步上升的态势",
    "技术团队在架构升级上做了大量工作这为后续扩展打下了基础",
    "我们同时也观察到在某些场景下仍然存在优化空间",
    "下一阶段的重点会放在性能提升和用户体验打磨上",
    "总结来说这一季度的表现符合预期并为后续奠定了良好基础",
    "好的然后呢我想再补充一下关于成本控制方面的内容",
    "就是那个呃我们在供应链环节做了一些调整效果还不错",
    "对吧所以这块的逻辑其实是这样的需要分两层来看",
    "嗯让我想想应该说这块数据反映出来的趋势是积极的",
    "刚才提到的那个问题其实我们在上次会议上已经讨论过了",
]


def _weighted_choice(rng: random.Random, choices):
    """Pick one element from ``[(value, weight), ...]`` using ``rng``."""
    total = sum(w for _, w in choices)
    roll = rng.random() * total
    acc = 0.0
    for value, weight in choices:
        acc += weight
        if roll <= acc:
            return value
    return choices[-1][0]


def _build_segments(
    rng: random.Random, count: int, media_duration: float
) -> list[Segment]:
    """Build a deterministic, time-sorted list of ``count`` segments.

    If ``media_duration`` is too small to hold all ``count`` segments at the
    configured distribution, the duration is implicitly extended -- callers
    should treat ``media_duration`` as a lower bound, not a hard cap, when
    constructing benchmarks.
    """
    segments: list[Segment] = []
    cursor = 0.5  # start a bit after 0 to leave room for typical intros

    silence_count = int(count * SILENCE_RATIO)
    subtitle_count = count - silence_count

    # Pre-decide which indices are silence (deterministic via rng).
    silence_indices = set(rng.sample(range(count), silence_count))

    for i in range(count):
        seg_id = f"seg-{i:05d}"
        is_silence = i in silence_indices

        if is_silence:
            duration = round(rng.uniform(*SILENCE_DURATION_RANGE), 3)
            seg_type = SegmentType.SILENCE
            text = ""
        else:
            duration = round(rng.uniform(*SUBTITLE_DURATION_RANGE), 3)
            seg_type = SegmentType.SUBTITLE
            chunks = rng.sample(_SAMPLE_TEXTS, k=rng.randint(1, 3))
            rng.shuffle(chunks)
            text = "".join(chunks)

        end = cursor + duration
        gap = round(rng.uniform(*INTER_SEGMENT_GAP_RANGE), 3)
        segments.append(
            Segment(
                id=seg_id,
                type=seg_type,
                start=round(cursor, 3),
                end=end,
                text=text,
                dirty_flags={"auto_generated": True} if is_silence else {},
            )
        )
        cursor = end + gap

    return segments


def _build_edits(
    rng: random.Random, segments: list[Segment], count: int
) -> list[EditDecision]:
    """Build ``count`` EditDecisions anchored on real segment time ranges.

    Each edit references a real segment window so that downstream consumers
    (e.g. ``DeleteRangesOverlay``) see realistic range distributions.
    """
    if not segments:
        return []

    subtitle_segments = [s for s in segments if s.type == SegmentType.SUBTITLE]
    if not subtitle_segments:
        subtitle_segments = segments

    edits: list[EditDecision] = []
    seen_targets: set[str] = set()

    for i in range(count):
        # Pick a target segment; allow duplicates (multiple edits per segment
        # is common in real projects), but bias toward unique ones.
        for _attempt in range(4):
            target = rng.choice(subtitle_segments)
            key = f"{target.id}:{target.start}:{target.end}"
            if key not in seen_targets or rng.random() < 0.15:
                seen_targets.add(key)
                break

        source = _weighted_choice(rng, EDIT_SOURCE_WEIGHTS)
        status = _weighted_choice(rng, EDIT_STATUS_WEIGHTS)
        action = "delete" if source != "subtitle_correction" else "keep"

        # For LLM smart-delete edits, narrow the range to a sub-window of the
        # target segment to mimic filler-word removal boundaries.
        if source == "llm_smart_delete" and (target.end - target.start) > 1.0:
            inner_start = target.start + rng.uniform(0.1, 0.4)
            inner_end = target.end - rng.uniform(0.1, 0.4)
            if inner_end > inner_start:
                edit_start = round(inner_start, 3)
                edit_end = round(inner_end, 3)
            else:
                edit_start, edit_end = target.start, target.end
        else:
            edit_start, edit_end = target.start, target.end

        edits.append(
            EditDecision(
                id=f"edit-{i:05d}",
                start=edit_start,
                end=edit_end,
                action=action,
                source=source,
                status=status,
                target_type="segment",
                target_id=target.id,
            )
        )

    return edits


def generate_synthetic_project(
    *,
    segment_count: int = DEFAULT_SEGMENT_COUNT,
    edit_count: int = DEFAULT_EDIT_COUNT,
    seed: int = DEFAULT_SEED,
    media_duration: float = 3600.0,
    project_name: str = "synthetic-baseline",
) -> Project:
    """Return a deterministic synthetic :class:`Project`.

    Parameters mirror the v2.3.2 evaluation plan §4 阶段 0 targets:
    1167 segments / 989 edits by default. Pass smaller sizes for fast
    smoke tests in CI.
    """
    rng = random.Random(seed)

    segments = _build_segments(rng, segment_count, media_duration)
    edits = _build_edits(rng, segments, edit_count)

    # Extend media duration if generated segments overshoot the requested
    # lower bound (deterministic given the seed).
    actual_end = segments[-1].end if segments else media_duration
    if actual_end + 1.0 > media_duration:
        media_duration = round(actual_end + 30.0, 3)

    timeline = Timeline(
        id="default",
        label="原始",
        source="synthetic",
        created_at=DEFAULT_CREATED_AT,
        transcript=TranscriptData(
            engine="synthetic", language="zh-CN", segments=segments
        ),
        edits=edits,
    )

    media = MediaInfo(
        path=f"/tmp/synthetic/{project_name}.mp4",
        media_hash=f"synthetic-{seed:08x}",
        duration=media_duration,
        format="mp4",
        width=1920,
        height=1080,
        fps=30.0,
        pix_fmt="yuv420p",
        audio_channels=2,
        sample_rate=48000,
        bit_rate=8_000_000,
    )

    project = Project(
        schema_version=2,
        project=ProjectMeta(name=project_name, created_at=DEFAULT_CREATED_AT, updated_at=DEFAULT_CREATED_AT),
        media=media,
        timelines=[timeline],
        active_timeline_id="default",
    )
    return project


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic Project JSON for v2.3.2 baselines."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output .json path (parent directories are created).",
    )
    parser.add_argument(
        "--segments",
        type=int,
        default=DEFAULT_SEGMENT_COUNT,
        help=f"Segment count (default {DEFAULT_SEGMENT_COUNT}).",
    )
    parser.add_argument(
        "--edits",
        type=int,
        default=DEFAULT_EDIT_COUNT,
        help=f"Edit count (default {DEFAULT_EDIT_COUNT}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed for deterministic output (default {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--media-duration",
        type=float,
        default=3600.0,
        help="Synthetic media duration in seconds (default 3600).",
    )
    parser.add_argument(
        "--name",
        default="synthetic-baseline",
        help="Synthetic project name.",
    )
    args = parser.parse_args()

    project = generate_synthetic_project(
        segment_count=args.segments,
        edit_count=args.edits,
        seed=args.seed,
        media_duration=args.media_duration,
        project_name=args.name,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        project.model_dump_json(indent=2), encoding="utf-8"
    )

    # Stats line for quick eyeball-check.
    timeline = project.active_timeline
    subtitle_count = sum(
        1 for s in timeline.transcript.segments if s.type == SegmentType.SUBTITLE
    )
    silence_count = sum(
        1 for s in timeline.transcript.segments if s.type == SegmentType.SILENCE
    )
    size_kb = args.output.stat().st_size / 1024
    print(
        f"wrote {args.output} "
        f"(segments={len(timeline.transcript.segments)} "
        f"subtitle={subtitle_count} silence={silence_count} "
        f"edits={len(timeline.edits)} "
        f"size={size_kb:.1f} KB seed={args.seed})"
    )


if __name__ == "__main__":
    _main()
