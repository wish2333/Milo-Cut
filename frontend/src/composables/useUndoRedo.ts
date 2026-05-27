import { ref, computed } from "vue"
import type { Project } from "@/types/project"

const DEFAULT_MAX_HISTORY = 50
const LARGE_SNAPSHOT_THRESHOLD = 2 * 1024 * 1024 // 2MB
const REDUCED_MAX_HISTORY = 10

export function useUndoRedo() {
  const undoStack = ref<string[]>([])
  const redoStack = ref<string[]>([])

  function getEffectiveMaxHistory(): number {
    if (undoStack.value.length > 0) {
      const lastSize = undoStack.value[undoStack.value.length - 1].length
      if (lastSize > LARGE_SNAPSHOT_THRESHOLD) {
        return REDUCED_MAX_HISTORY
      }
    }
    return DEFAULT_MAX_HISTORY
  }

  function pushSnapshot(project: Project) {
    const serialized = JSON.stringify(project)
    undoStack.value = [...undoStack.value, serialized]
    const maxHistory = getEffectiveMaxHistory()
    while (undoStack.value.length > maxHistory) {
      undoStack.value = undoStack.value.slice(1)
    }
    redoStack.value = []
  }

  function undo(currentProject: Project): Project | null {
    if (undoStack.value.length === 0) return null
    const newUndo = [...undoStack.value]
    const snapshot = newUndo.pop()!
    undoStack.value = newUndo
    redoStack.value = [...redoStack.value, JSON.stringify(currentProject)]
    return JSON.parse(snapshot)
  }

  function redo(currentProject: Project): Project | null {
    if (redoStack.value.length === 0) return null
    const newRedo = [...redoStack.value]
    const snapshot = newRedo.pop()!
    redoStack.value = newRedo
    undoStack.value = [...undoStack.value, JSON.stringify(currentProject)]
    return JSON.parse(snapshot)
  }

  function clearHistory() {
    undoStack.value = []
    redoStack.value = []
  }

  return {
    undoStack,
    redoStack,
    pushSnapshot,
    undo,
    redo,
    clearHistory,
    canUndo: computed(() => undoStack.value.length > 0),
    canRedo: computed(() => redoStack.value.length > 0),
  }
}
