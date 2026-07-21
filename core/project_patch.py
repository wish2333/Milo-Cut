"""ProjectPatch application utilities.

See ``core/models.py:ProjectPatch`` for the schema contract and
``docs/2.3.0/2.3.2-record.md`` 阶段 2 for design rationale.
"""

from __future__ import annotations

from core.models import Project, ProjectPatch, Timeline


class PatchApplicationError(ValueError):
    """Raised when a patch cannot be applied to the given project."""


def apply_project_patch(project: Project, patch: ProjectPatch) -> Project:
    """Apply ``patch`` to ``project`` and return the resulting Project.

    The returned Project is a new instance (model_copy); ``project`` is
    not mutated. ``None`` patch fields are treated as "no change" and
    propagate the existing layer reference unchanged.

    Behaviour:

    - ``patch.full_project`` wins over everything else -- callers use it
      for timeline-switch / project-creation fallbacks.
    - Layer fields (``segments`` / ``edits`` / ``analysis``) replace the
      *active* timeline's corresponding layer (or ``timeline_id`` if
      explicitly set on the patch).
    - ``media`` / ``active_timeline_id`` are project-level overrides.

    Raises :class:`PatchApplicationError` if the patch references a
    ``timeline_id`` that does not exist on ``project``.
    """
    if patch.full_project is not None:
        return patch.full_project

    target_timeline_id = patch.timeline_id or project.active_timeline_id

    has_layer_updates = (
        patch.segments is not None
        or patch.edits is not None
        or patch.analysis is not None
    )

    if has_layer_updates:
        target_exists = any(tl.id == target_timeline_id for tl in project.timelines)
        if not target_exists:
            raise PatchApplicationError(
                f"Patch targets timeline_id={target_timeline_id!r} which does "
                f"not exist on project (available: {[tl.id for tl in project.timelines]})"
            )

    new_timelines: list[Timeline] = []
    for tl in project.timelines:
        if tl.id != target_timeline_id:
            new_timelines.append(tl)
            continue

        new_tl = tl
        if patch.segments is not None:
            new_transcript = new_tl.transcript.model_copy(
                update={"segments": list(patch.segments)}
            )
            new_tl = new_tl.model_copy(update={"transcript": new_transcript})
        if patch.edits is not None:
            new_tl = new_tl.model_copy(update={"edits": list(patch.edits)})
        if patch.analysis is not None:
            new_tl = new_tl.model_copy(update={"analysis": patch.analysis})
        new_timelines.append(new_tl)

    project_updates: dict = {"timelines": new_timelines}
    if patch.media is not None:
        project_updates["media"] = patch.media
    if patch.active_timeline_id is not None:
        project_updates["active_timeline_id"] = patch.active_timeline_id

    return project.model_copy(update=project_updates)


def is_stale_patch(patch: ProjectPatch, last_seen_revision: int) -> bool:
    """True when ``patch`` should be discarded as out-of-order.

    A patch is stale when its revision is not strictly greater than the
    last revision the frontend has already applied. ``last_seen_revision``
    starts at 0 (so the very first patch with ``revision >= 1`` is always
    fresh).
    """
    return patch.revision <= last_seen_revision
