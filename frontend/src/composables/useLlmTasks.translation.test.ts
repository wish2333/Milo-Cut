/**
 * v3.0.4 M1-6: useLlmTasks translation lifecycle tests.
 *
 * startTranslation follows the startSubtitleCorrection pattern (task state
 * + failure envelope -> errorMsg), and the singleton consumes
 * EVENT_LLM_TRANSLATION_COMPLETED into the module-level
 * lastTranslationCompletion ref that the WorkspacePage watcher drains.
 *
 * useLlmTasks keeps module-level singleton state, so every test re-imports
 * a FRESH module graph (vi.resetModules + dynamic import) instead of
 * sharing refs across cases.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { EVENT_LLM_TRANSLATION_COMPLETED, EVENT_DEMO_RESET } from "@/utils/events"

type EventHandler = (detail: unknown) => void
const eventHandlers = new Map<string, EventHandler[]>()
const callMock = vi.fn()

vi.mock("@/bridge", () => ({
  call: (...args: unknown[]) => callMock(...args),
  onEvent: (name: string, handler: EventHandler) => {
    const list = eventHandlers.get(name) ?? []
    list.push(handler)
    eventHandlers.set(name, list)
    return () => {}
  },
}))

async function freshLlmTasks() {
  vi.resetModules()
  eventHandlers.clear()
  const mod = await import("@/composables/useLlmTasks")
  return mod.useLlmTasks()
}

function fire(name: string, detail: unknown) {
  for (const h of eventHandlers.get(name) ?? []) h(detail)
}

const COMPLETION_PAYLOAD = {
  track_id: "trk_x",
  track_name: "English",
  language: "en",
  written_count: 30,
  target_count: 30,
  uncovered_ids: ["seg-1", "seg-7"],
  ledger: { uncovered_segment_ids: ["seg-1", "seg-7"] },
}

describe("useLlmTasks.startTranslation (M1-6)", () => {
  beforeEach(() => {
    callMock.mockReset()
  })

  it("calls start_translation with the language and stays running on success", async () => {
    callMock.mockResolvedValue({ success: true, data: { task_id: "t1", type: "llm_translation" } })
    const tasks = await freshLlmTasks()

    const ok = await tasks.startTranslation("ja")

    expect(ok).toBe(true)
    expect(callMock).toHaveBeenCalledWith("start_translation", "ja")
    expect(tasks.isRunning.value).toBe(true)
    expect(tasks.errorMsg.value).toBeNull()
    // Previous completion state is cleared when a new task starts.
    expect(tasks.lastTranslationCompletion.value).toBeNull()
  })

  it("returns false and surfaces the backend error on a rejected start", async () => {
    callMock.mockResolvedValue({
      success: false,
      error: "已存在同语言译文轨：可清空或删除该轨后重试",
    })
    const tasks = await freshLlmTasks()

    const ok = await tasks.startTranslation("zh-CN")

    expect(ok).toBe(false)
    expect(tasks.isRunning.value).toBe(false)
    expect(tasks.errorMsg.value).toContain("可清空或删除该轨后重试")
  })
})

describe("useLlmTasks EVENT_LLM_TRANSLATION_COMPLETED consumption (M1-6)", () => {
  beforeEach(() => {
    callMock.mockReset()
    callMock.mockResolvedValue({ success: false, error: "unexpected call" })
  })

  it("stores the completion payload into lastTranslationCompletion", async () => {
    const tasks = await freshLlmTasks()
    tasks.isRunning.value = true

    fire(EVENT_LLM_TRANSLATION_COMPLETED, COMPLETION_PAYLOAD)

    expect(tasks.isRunning.value).toBe(false)
    expect(tasks.lastTranslationCompletion.value).toEqual({
      track_id: "trk_x",
      track_name: "English",
      language: "en",
      uncovered_ids: ["seg-1", "seg-7"],
    })
  })

  it("re-populates after the consumer clears the ref (consecutive completions)", async () => {
    const tasks = await freshLlmTasks()
    fire(EVENT_LLM_TRANSLATION_COMPLETED, COMPLETION_PAYLOAD)
    expect(tasks.lastTranslationCompletion.value).not.toBeNull()

    // WorkspacePage watcher drains the ref after switching the track.
    tasks.lastTranslationCompletion.value = null
    expect(tasks.lastTranslationCompletion.value).toBeNull()

    fire(EVENT_LLM_TRANSLATION_COMPLETED, {
      ...COMPLETION_PAYLOAD,
      track_id: "trk_y",
      uncovered_ids: [],
    })
    expect(tasks.lastTranslationCompletion.value).toEqual({
      track_id: "trk_y",
      track_name: "English",
      language: "en",
      uncovered_ids: [],
    })
  })

  it("ignores completions without a track_id and clears on demo reset", async () => {
    const tasks = await freshLlmTasks()

    fire(EVENT_LLM_TRANSLATION_COMPLETED, { track_id: "", uncovered_ids: [] })
    expect(tasks.lastTranslationCompletion.value).toBeNull()

    fire(EVENT_LLM_TRANSLATION_COMPLETED, COMPLETION_PAYLOAD)
    expect(tasks.lastTranslationCompletion.value).not.toBeNull()

    fire(EVENT_DEMO_RESET, undefined)
    expect(tasks.lastTranslationCompletion.value).toBeNull()
  })
})
