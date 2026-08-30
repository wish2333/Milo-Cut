/**
 * Shared monotonic revision tracker (v3.0.0 M5).
 *
 * App.vue remains the single writer (it is the only place that applies
 * patch envelopes); useUndoRedo reads it as ``base_revision`` for the
 * backend ``apply_undo`` call. Module-level ref so it survives across
 * composable instances without provide/inject plumbing.
 */
import { ref } from "vue"

export const lastSeenRevision = ref(0)

export function noteRevision(revision: number): void {
  if (revision > lastSeenRevision.value) {
    lastSeenRevision.value = revision
  }
}
