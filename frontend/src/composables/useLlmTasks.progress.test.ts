/**
 * v3.0.4 smoke-fix regression tests (P4-4 first real-device pass).
 *
 * 1b. The panel progress bar never listened to the generic task:progress
 *     stream -- ensureListeners now writes detail.percent into the shared
 *     progress ref while an LLM task is running (UI single-flight makes
 *     "any progress event while isRunning" unambiguous).
 * 1a. loadLlmConfig judges "configured" on the provider-RESOLVED
 *     base_url/model (empty raw fields fall back to provider defaults and
 *     must not flag the setup as 未配置).
 *
 * Same isolation strategy as useLlmTasks.translation.test.ts: the module
 * holds singleton refs, so every case re-imports a FRESH module graph
 * (vi.resetModules + dynamic import).
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  EVENT_TASK_PROGRESS,
  EVENT_TASK_CANCELLED,
  EVENT_LLM_ANALYSIS_FAILED,
  EVENT_LLM_TRANSLATION_COMPLETED,
} from "@/utils/events"

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

describe("useLlmTasks task:progress consumption (smoke-fix 1b)", () => {
  beforeEach(() => {
    callMock.mockReset()
  })

  it("writes detail.percent into progress while a translation task is running", async () => {
    // Enter the running state through the production path: a successful
    // startTranslation leaves isRunning true (task accepted by backend).
    callMock.mockResolvedValue({ success: true, data: { task_id: "t1", type: "llm_translation" } })
    const tasks = await freshLlmTasks()
    const ok = await tasks.startTranslation("ja")
    expect(ok).toBe(true)
    expect(tasks.isRunning.value).toBe(true)
    expect(tasks.progress.value).toBe(0)

    fire(EVENT_TASK_PROGRESS, {
      task_id: "t1",
      percent: 42,
      message: "Translation batch 5/12...",
    })
    expect(tasks.progress.value).toBe(42)

    // Later batches keep updating the same ref (no reset between events).
    fire(EVENT_TASK_PROGRESS, { task_id: "t1", percent: 83.5 })
    expect(tasks.progress.value).toBe(83.5)
  })

  it("ignores task:progress once the task is no longer running (completion path)", async () => {
    callMock.mockResolvedValue({ success: true, data: { task_id: "t2", type: "llm_translation" } })
    const tasks = await freshLlmTasks()
    await tasks.startTranslation("en")
    fire(EVENT_TASK_PROGRESS, { task_id: "t2", percent: 42 })
    expect(tasks.progress.value).toBe(42)

    // Completion flips isRunning off (last progress value is kept for the
    // finished bar); stray late progress events must NOT overwrite it.
    fire(EVENT_LLM_TRANSLATION_COMPLETED, {
      track_id: "trk_x",
      track_name: "English",
      language: "en",
      uncovered_ids: [],
    })
    expect(tasks.isRunning.value).toBe(false)

    fire(EVENT_TASK_PROGRESS, { task_id: "t2", percent: 99 })
    expect(tasks.progress.value).toBe(42)
  })

  it("ignores task:progress entirely while no task was ever started", async () => {
    callMock.mockResolvedValue({ success: false, error: "unexpected call" })
    const tasks = await freshLlmTasks()
    expect(tasks.isRunning.value).toBe(false)

    fire(EVENT_TASK_PROGRESS, { task_id: "other", percent: 42 })
    expect(tasks.progress.value).toBe(0)
  })

  it("ignores progress payloads without a numeric percent", async () => {
    callMock.mockResolvedValue({ success: true, data: { task_id: "t3", type: "llm_translation" } })
    const tasks = await freshLlmTasks()
    await tasks.startTranslation("ja")
    fire(EVENT_TASK_PROGRESS, { task_id: "t3", percent: 42 })
    expect(tasks.progress.value).toBe(42)

    fire(EVENT_TASK_PROGRESS, { task_id: "t3", percent: "42" }) // string
    fire(EVENT_TASK_PROGRESS, { task_id: "t3", message: "no percent field" }) // absent
    fire(EVENT_TASK_PROGRESS, undefined) // malformed detail
    expect(tasks.progress.value).toBe(42)
  })
})

describe("useLlmTasks.loadLlmConfig resolved-field judgment (smoke-fix 1a)", () => {
  beforeEach(() => {
    callMock.mockReset()
  })

  it("treats empty raw fields with provider defaults as configured", async () => {
    // Real-device finding: base_url/model left empty (provider defaults)
    // were judged 未配置 even though the settings test button worked.
    callMock.mockResolvedValue({
      success: true,
      data: {
        provider: "deepseek",
        model: "",
        base_url: "",
        api_key_masked: "sk-***key",
        resolved_model: "deepseek-chat",
        resolved_base_url: "https://api.deepseek.com",
      },
    })
    const tasks = await freshLlmTasks()

    await tasks.loadLlmConfig()

    expect(tasks.llmConfig.value.configured).toBe(true)
    expect(tasks.llmConfig.value.model).toBe("deepseek-chat")
    expect(tasks.llmConfig.value.baseUrl).toBe("https://api.deepseek.com")
  })

  it("stays unconfigured when the resolved fields are empty too (no api key)", async () => {
    callMock.mockResolvedValue({
      success: true,
      data: {
        provider: "deepseek",
        model: "",
        base_url: "",
        api_key_masked: "",
        resolved_model: "deepseek-chat",
        resolved_base_url: "https://api.deepseek.com",
      },
    })
    const tasks = await freshLlmTasks()

    await tasks.loadLlmConfig()

    expect(tasks.llmConfig.value.configured).toBe(false)
  })

  it("falls back to the raw fields when resolved ones are absent (older backend)", async () => {
    callMock.mockResolvedValue({
      success: true,
      data: {
        provider: "custom",
        model: "my-model",
        base_url: "https://my.example/v1",
        api_key_masked: "sk-***xyz",
      },
    })
    const tasks = await freshLlmTasks()

    await tasks.loadLlmConfig()

    expect(tasks.llmConfig.value.configured).toBe(true)
    expect(tasks.llmConfig.value.model).toBe("my-model")
    expect(tasks.llmConfig.value.baseUrl).toBe("https://my.example/v1")
  })
})

// ---------------------------------------------------------------------------
// v3.0.5 R5.1 (M5.1): progress message twin + translation cancel error reset
// ---------------------------------------------------------------------------

describe("useLlmTasks progressMessage + cancel error clearing (v3.0.5 R5.1)", () => {
  beforeEach(() => {
    callMock.mockReset()
  })

  it("stores detail.message into progressMessage while running (serial-downgrade signal source)", async () => {
    callMock.mockResolvedValue({ success: true, data: { task_id: "t1", type: "llm_translation" } })
    const tasks = await freshLlmTasks()
    await tasks.startTranslation("en")
    expect(tasks.progressMessage.value).toBeNull() // reset at task start

    fire(EVENT_TASK_PROGRESS, {
      task_id: "t1",
      percent: 40,
      message: "Translation batch 3/8 (serial)...",
    })
    expect(tasks.progress.value).toBe(40)
    expect(tasks.progressMessage.value).toBe("Translation batch 3/8 (serial)...")

    // plain messages overwrite the serial one (no sticky notice)
    fire(EVENT_TASK_PROGRESS, { task_id: "t1", percent: 55, message: "Translation batch 4/8..." })
    expect(tasks.progressMessage.value).toBe("Translation batch 4/8...")
  })

  it("translation cancel clears errorMsg (SG2-2: task_type-scoped)", async () => {
    callMock.mockResolvedValue({ success: true, data: { task_id: "t2", type: "llm_translation" } })
    const tasks = await freshLlmTasks()
    await tasks.startTranslation("en")

    // a failed earlier run left the error behind
    fire(EVENT_LLM_ANALYSIS_FAILED, { error: "Translation incomplete: boom" })
    expect(tasks.errorMsg.value).toBe("Translation incomplete: boom")

    fire(EVENT_TASK_CANCELLED, { task_id: "t2", task_type: "llm_translation" })
    expect(tasks.isRunning.value).toBe(false)
    expect(tasks.progress.value).toBe(0)
    expect(tasks.errorMsg.value).toBeNull() // residual cleared
  })

  it("non-translation cancel keeps errorMsg (existing defect, out of scope)", async () => {
    callMock.mockResolvedValue({ success: true, data: { task_id: "t3", type: "llm_subtitle_correction" } })
    const tasks = await freshLlmTasks()
    await tasks.startSubtitleCorrection()

    fire(EVENT_LLM_ANALYSIS_FAILED, { error: "correction failed" })
    fire(EVENT_TASK_CANCELLED, { task_id: "t3", task_type: "llm_subtitle_correction" })

    expect(tasks.errorMsg.value).toBe("correction failed") // untouched (record §8 legacy)
    expect(tasks.isRunning.value).toBe(false)
  })
})
