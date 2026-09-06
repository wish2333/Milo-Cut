"""Project schema migration chain (v3.0.0 M10, moved verbatim from ProjectService).

Pure move: v1->v2 dict wrapping plus the post-load instance migrations.
``run_post_load_migrations`` preserves the original call order from
``open_project``. Behavior must remain byte-for-byte identical (the pytest
suite anchors this).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from core.models import EditDecision, EditStatus, SegmentType

if TYPE_CHECKING:
    from core.project_service import ProjectService

__all__ = [
    "migrate_v1_to_v2",
    "migrate_silence_edits",
    "dedupe_edit_ids",
    "migrate_highlights",
    "migrate_overlapping_silence_edits",
    "run_post_load_migrations",
]


def migrate_v1_to_v2(raw: dict) -> dict:
        """Migrate schema_version 1 -> 2: wrap flat fields into default Timeline."""
        if raw.get("schema_version", 1) >= 2:
            return raw

        transcript = raw.pop("transcript", {"segments": []})
        edits = raw.pop("edits", [])
        analysis = raw.pop("analysis", {"results": []})
        raw.pop("topic_drift", None)  # Drop old Topic Drift data

        created_at = raw.get("project", {}).get("created_at", "")
        raw["timelines"] = [
            {
                "id": "default",
                "label": "原始",
                "source": "migrated",
                "created_at": created_at,
                "parent_id": "",
                "transcript": transcript,
                "edits": edits,
                "analysis": analysis,
            }
        ]
        raw["active_timeline_id"] = "default"
        raw["schema_version"] = 2
        return raw

def migrate_silence_edits(service: ProjectService) -> None:
        """Migrate old format silence EditDecisions to bind target_id."""
        if not service._current:
            return

        silence_map = {
            s.id: s for s in service.active_timeline.transcript.segments
            if s.type == SegmentType.SILENCE
        }

        migrated = []
        for edit in service.active_timeline.edits:
            if (edit.source == "silence_detection"
                    and edit.target_type == "range"
                    and edit.target_id is None):
                # Try to match by time range
                matched = next(
                    (s for s in silence_map.values()
                     if abs(s.start - edit.start) < 0.05 and abs(s.end - edit.end) < 0.05),
                    None,
                )
                if matched:
                    migrated.append(edit.model_copy(update={
                        "target_type": "segment",
                        "target_id": matched.id,
                    }))
                else:
                    migrated.append(edit)
            else:
                migrated.append(edit)

        service._update_active_timeline(edits=migrated)

def dedupe_edit_ids(service: ProjectService) -> None:
        """One-time fix: append _dup{N} suffix to duplicate edit ids in the active timeline.

        Suffix format matches the defensive logic in add_analysis_results (_dup{N}).
        O(n) fast path skips projects with no duplicates (zero overhead for large projects).
        """
        if not service._current:
            return

        tl = service.active_timeline
        edits = list(tl.edits)
        ids = [e.id for e in edits]

        # Fast path: no duplicates, skip entirely
        if len(ids) == len(set(ids)):
            return

        # Duplicate detected -- back up and fix
        all_ids = set(ids)
        seen: dict[str, int] = {}
        fixed = []
        changed_count = 0

        for e in edits:
            if e.id in seen:
                seen[e.id] += 1
                candidate = f"{e.id}_dup{seen[e.id]}"
                # Guard: candidate might collide with an existing id (secondary conflict)
                while candidate in all_ids:
                    seen[e.id] += 1
                    candidate = f"{e.id}_dup{seen[e.id]}"
                all_ids.add(candidate)
                fixed.append(e.model_copy(update={"id": candidate}))
                changed_count += 1
            else:
                seen[e.id] = 1
                fixed.append(e)

        if changed_count > 0:
            logger.warning("Deduped {} duplicate edit ids in timeline {}", changed_count, tl.id)
            service._update_active_timeline(edits=fixed)

def migrate_highlights(service: ProjectService) -> None:
        """One-time migration: fix legacy EditDecisions created before Bug E/G fix.

        - Remove ANY orphan EditDecision whose analysis_id no longer exists
          (not limited to highlights; covers all analysis-driven sources)
        - Set action="keep" for highlight-source EditDecisions still on "delete"
        Idempotent: safe to run multiple times.
        """
        if not service._current:
            return

        tl = service.active_timeline
        ar_ids = {r.id for r in tl.analysis.results}

        updated_edits = []
        fixed = 0
        orphan_removed = 0
        for e in tl.edits:
            is_highlight = e.source in ("llm_highlight", "manual_highlight")
            # An edit with analysis_id pointing at a non-existent result is an
            # orphan regardless of source -- its driving analysis was deleted.
            if e.analysis_id and e.analysis_id not in ar_ids:
                orphan_removed += 1
                continue

            if is_highlight and e.action == "delete":
                # Bug E legacy: highlight edit had wrong action
                updated_edits.append(e.model_copy(update={"action": "keep"}))
                fixed += 1
            else:
                updated_edits.append(e)

        if fixed > 0 or orphan_removed > 0:
            service._update_active_timeline(edits=updated_edits)
            logger.info(
                "Highlight migration: fixed %d actions, removed %d orphans",
                fixed, orphan_removed,
            )

def migrate_overlapping_silence_edits(service: ProjectService) -> None:
        """Repair silence_detection edits that conflict with prior user decisions.

        Background: older versions of add_silence_results used exact 0.05s
        time-range matching for deduplication, so silence_detection edits could
        be auto-created and then confirmed by bulk actions in ranges where the
        user had already rejected deletion. The frontend's resolveSegmentState
        would then show "confirmed delete" on a subtitle the user wanted to keep.

        This migration marks confirmed silence_detection edits as REJECTED when
        they overlap (>0.3s) a user edit whose effective intent is "keep".
        Idempotent: safe to run multiple times.
        """
        if not service._current:
            return

        tl = service.active_timeline
        edits = list(tl.edits)

        user_edits = [e for e in edits if e.source == "user"]
        if not user_edits:
            return

        updated: list[EditDecision] = []
        changed = 0
        for e in edits:
            if e.source != "silence_detection" or e.status != EditStatus.CONFIRMED:
                updated.append(e)
                continue

            # Effective intent "keep" = user rejected delete OR confirmed keep
            conflict = any(
                service._ranges_overlap(e.start, e.end, ue.start, ue.end)
                and (
                    (ue.status == EditStatus.REJECTED and ue.action == "delete")
                    or (ue.status == EditStatus.CONFIRMED and ue.action == "keep")
                )
                for ue in user_edits
            )

            if conflict:
                updated.append(e.model_copy(update={"status": EditStatus.REJECTED}))
                changed += 1
            else:
                updated.append(e)

        if changed > 0:
            service._update_active_timeline(edits=updated)
            logger.info(
                "Silence overlap migration: rejected {} conflicting silence edits",
                changed,
            )


def run_post_load_migrations(service: ProjectService) -> None:
    """Run the post-load migration chain (original open_project order)."""
    # Migrate old format silence edits
    migrate_silence_edits(service)

    # v2.1.1: Dedupe duplicate edit ids (legacy llm_smart bug fix)
    dedupe_edit_ids(service)

    # v2.1.1: Migrate legacy highlight EditDecisions (Bug E/G fix)
    migrate_highlights(service)

    # v2.1.2: Reject silence_detection edits that overwrite prior user
    # decisions (overlap-based repair; replaces fragile exact-time check)
    migrate_overlapping_silence_edits(service)
