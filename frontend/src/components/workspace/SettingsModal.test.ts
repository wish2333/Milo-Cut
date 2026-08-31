/**
 * SettingsModal tests (v2.1.0 Phase 4 preset management + v3.0.0 M8-1 split).
 *
 * Part 1 verifies the preset composable integration points in isolation
 * (preset CRUD API surface, mocked).
 * Part 2 (M8-1) verifies the tab split: SettingsModal keeps tab switching +
 * settings load/save, tab components mount lazily via v-if, so inactive
 * tabs hold zero component instances.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount, flushPromises } from "@vue/test-utils"
import { ref } from "vue"

// Create reactive refs for preset state
const _presetsByFunc = ref<Record<string, Array<{id: string; name: string}>>>({})
const _loadPresets = vi.fn()
const _applyPreset = vi.fn()
const _savePreset = vi.fn()
const _deletePreset = vi.fn()

// Full composable surface (LlmSettingsTab destructures all of it)
const _testing = ref(false)
const _testResult = ref<{ success: boolean; message: string } | null>(null)
const _promptsData = ref<unknown>(null)
const _loadPrompts = vi.fn()
const _updatePrompt = vi.fn()
const _resetPrompt = vi.fn()
const _testConnection = vi.fn()

vi.mock("@/composables/useLlmSettings", () => ({
  useLlmSettings: () => ({
    testing: _testing,
    testResult: _testResult,
    testConnection: _testConnection,
    promptsData: _promptsData,
    loadingPrompts: ref(false),
    loadPrompts: _loadPrompts,
    updatePrompt: _updatePrompt,
    resetPrompt: _resetPrompt,
    presetsByFunc: _presetsByFunc,
    loadingPresets: ref({}),
    loadPresets: _loadPresets,
    savePreset: _savePreset,
    applyPreset: _applyPreset,
    deletePreset: _deletePreset,
  }),
}))

// Bridge mock: get_settings resolves a stub settings object, everything
// else resolves a guarded failure so tab onMounted loads stay inert.
const stubSettings = {
  ffmpeg_path: "", ffprobe_path: "",
  silence_threshold_db: -30, silence_min_duration: 0.5,
  silence_margin: 0.15, silence_subtitle_padding: 0,
  trim_subtitles_on_silence_overlap: false,
  proxy_resolution: "1280x720", auto_generate_proxy: false,
  model_dir: "",
  llm_provider: "deepseek", llm_base_url: "", llm_api_key: "", llm_model: "",
  llm_temperature: 0.1, llm_thinking_enabled: false,
  asr_engine: "faster-whisper", asr_plugin_id: "", asr_model_size: "",
  asr_language: "zh", asr_device: "cpu",
  whisper_compute_type: "int8", qwen_compute_type: "float32",
  asr_vad_filter: false, duplicate_threshold: 0.8,
  export_video_codec: "libx264", export_audio_codec: "aac",
  export_audio_bitrate: "192k", export_preset: "medium", export_crf: 23,
  export_resolution: "original", export_ffmpeg_transitions: false,
  export_ffmpeg_fade_duration: 0.5, export_ffmpeg_fade_mode: "crossfade",
}

const _call = vi.fn(async (method?: string) =>
  method === "get_settings"
    ? { success: true, data: { ...stubSettings } }
    : { success: false },
)
vi.mock("@/bridge", () => ({
  call: (...args: unknown[]) => _call(...(args as [string?])),
  onEvent: vi.fn(),
}))

import SettingsModal from "./SettingsModal.vue"
import GeneralSettingsTab from "./settings/GeneralSettingsTab.vue"
import LlmSettingsTab from "./settings/LlmSettingsTab.vue"

describe("Preset management integration (SettingsModal Phase 1)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _presetsByFunc.value = {}
  })

  it("loadPresets is callable for a preset-supported feature", async () => {
    const mod = await import("@/composables/useLlmSettings")
    const { loadPresets } = mod.useLlmSettings()

    await loadPresets("smart_delete")

    expect(_loadPresets).toHaveBeenCalledWith("smart_delete")
  })

  it("presetsByFunc starts empty", () => {
    expect(_presetsByFunc.value).toEqual({})
  })

  it("applyPreset is callable with func_key and preset_id", async () => {
    const mod = await import("@/composables/useLlmSettings")
    const { applyPreset } = mod.useLlmSettings()

    await applyPreset("smart_delete", "preset-abc")

    expect(_applyPreset).toHaveBeenCalledWith("smart_delete", "preset-abc")
  })

  it("savePreset is callable with func_key, name and params", async () => {
    const mod = await import("@/composables/useLlmSettings")
    const settings = mod.useLlmSettings() as unknown as {
      savePreset: (funcKey: string, name: string, params?: Record<string, string[]>, systemOverride?: string) => Promise<void>
    }

    await settings.savePreset("smart_delete", "学术报告")

    expect(_savePreset).toHaveBeenCalledWith("smart_delete", "学术报告")
  })

  it("deletePreset is callable with preset_id", async () => {
    const mod = await import("@/composables/useLlmSettings")
    const { deletePreset } = mod.useLlmSettings()

    await deletePreset("smart_delete", "preset-abc")

    expect(_deletePreset).toHaveBeenCalledWith("smart_delete", "preset-abc")
  })

  it("presetsByFunc can be populated with preset data", () => {
    _presetsByFunc.value = {
      smart_delete: [
        { id: "default", name: "默认" },
        { id: "preset-1", name: "学术报告" },
      ],
    }

    expect(_presetsByFunc.value.smart_delete).toHaveLength(2)
    expect(_presetsByFunc.value.smart_delete[0].id).toBe("default")
    expect(_presetsByFunc.value.smart_delete[1].name).toBe("学术报告")
  })
})

describe("SettingsModal tab split (v3.0.0 M8-1)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function mountModal() {
    const wrapper = mount(SettingsModal, {
      props: { visible: true },
      global: { stubs: { teleport: true } },
    })
    await flushPromises()
    return wrapper
  }

  it("renders only the active tab (general) on open", async () => {
    const wrapper = await mountModal()

    expect(wrapper.findComponent(GeneralSettingsTab).exists()).toBe(true)
    expect(wrapper.findComponent(LlmSettingsTab).exists()).toBe(false)
  })

  it("switching tabs swaps the mounted tab instance (lazy mount)", async () => {
    const wrapper = await mountModal()

    // Tab nav order: general / ai-engine / llm / export / shortcuts
    await wrapper.findAll('[role="tab"]')[2].trigger("click")
    await flushPromises()

    expect(wrapper.findComponent(LlmSettingsTab).exists()).toBe(true)
    expect(wrapper.findComponent(GeneralSettingsTab).exists()).toBe(false)
  })

  it("loads settings from get_settings on mount", async () => {
    await mountModal()

    expect(_call).toHaveBeenCalledWith("get_settings")
  })
})
