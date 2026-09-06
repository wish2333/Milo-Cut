/**
 * useAsrEngines tests (v3.0.0 M8-2b).
 *
 * Locks the single-source contract: WorkspacePage and the settings tabs
 * consume the same module-singleton state (changing a default or selection
 * in one UI is immediately visible in the other), the pluginId watcher
 * derives engine + device/compute, persistence uses engine-prefixed keys,
 * and the settings-modal patch derivation matches the original logic.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { nextTick } from "vue"

const _call = vi.fn()
vi.mock("@/bridge", () => ({
  call: (...args: unknown[]) => _call(...(args as [string, ...unknown[]])),
  onEvent: vi.fn(),
}))

import {
  useAsrEngines,
  deriveEngineChangePatch,
  type InstalledEngine,
} from "./useAsrEngines"

const whisperCpu: InstalledEngine = {
  engine: "faster-whisper",
  displayName: "Faster Whisper ASR (CPU)",
  pluginId: "plugin-whisper-cpu",
  ready: true,
}

describe("useAsrEngines (M8-2b single source)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _call.mockResolvedValue({ success: false })
    // Reset singleton state between tests
    const s = useAsrEngines()
    s.asrPluginId.value = ""
    s.asrEngine.value = "faster-whisper"
    s.installedEngines.value = []
  })

  it("two consumers share the same singleton refs", () => {
    const a = useAsrEngines()
    const b = useAsrEngines()

    expect(a.asrEngine).toBe(b.asrEngine)
    expect(a.asrPluginId).toBe(b.asrPluginId)
    expect(a.asrSettingsPerEngine).toBe(b.asrSettingsPerEngine)

    // A change through one consumer is visible through the other
    a.asrEngine.value = "qwen3-asr"
    expect(b.asrEngine.value).toBe("qwen3-asr")
  })

  it("selecting a CPU plugin of the same engine updates device", async () => {
    const s = useAsrEngines()
    s.installedEngines.value = [whisperCpu]
    s.asrPluginId.value = "plugin-whisper-cpu"
    await nextTick()

    // Same engine type: watcher keeps engine, adjusts device for -cpu suffix
    expect(s.asrEngine.value).toBe("faster-whisper")
    expect(s.asrSettingsPerEngine.value["faster-whisper"].device).toBe("cpu")
  })

  it("saveAsrSettings persists engine-prefixed keys", async () => {
    _call.mockResolvedValue({ success: true })
    const s = useAsrEngines()
    s.asrPluginId.value = "plugin-whisper-cpu"
    await nextTick()
    s.asrSettingsPerEngine.value["faster-whisper"].model_size = "custom-model"

    const ok = await s.saveAsrSettings()

    expect(ok).toBe(true)
    expect(_call).toHaveBeenCalledWith("update_settings", expect.objectContaining({
      asr_engine: "faster-whisper",
      asr_plugin_id: "plugin-whisper-cpu",
      asr_model_size: "custom-model",
      whisper_compute_type: expect.any(String),
      whisper_vad_threshold: expect.any(Number),
      whisper_vad_min_silence_ms: expect.any(Number),
    }))
    const payload = _call.mock.calls.find(c => c[0] === "update_settings")?.[1] as Record<string, unknown>
    expect(payload).not.toHaveProperty("qwen_compute_type")
    expect(payload).not.toHaveProperty("asr_compute_type")
  })

  it("deriveEngineChangePatch emits engine-specific defaults", () => {
    const qwenPatch = deriveEngineChangePatch("plugin-qwen-gpu", "qwen3-asr") as Record<string, unknown>
    expect(qwenPatch).toMatchObject({
      asr_plugin_id: "plugin-qwen-gpu",
      asr_engine: "qwen3-asr",
      asr_language: "auto",
      qwen_compute_type: "bfloat16",
    })

    const whisperPatch = deriveEngineChangePatch("plugin-whisper-cpu", "faster-whisper") as Record<string, unknown>
    expect(whisperPatch).toMatchObject({
      asr_plugin_id: "plugin-whisper-cpu",
      asr_engine: "faster-whisper",
      asr_language: "zh",
      whisper_compute_type: "int8",
    })
    // Device depends on platform (macOS has no CUDA): CPU plugin on macOS
    // falls back to whisper's "auto", elsewhere to plain "cpu".
    const isMac = navigator.platform.toLowerCase().includes("mac")
    expect(whisperPatch.asr_device).toBe(isMac ? "auto" : "cpu")

    expect(deriveEngineChangePatch("", "faster-whisper")).toBeNull()
  })
})
