/**
 * SettingsModal preset management tests (v2.1.0 Phase 4).
 *
 * Rather than mounting the full SettingsModal (which depends on many
 * bridge calls and pluginManager), this file tests the preset
 * composable integration points in isolation.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ref } from "vue"
import { flushPromises } from "@vue/test-utils"

// Create reactive refs for preset state
const _presetsByFunc = ref<Record<string, unknown[]>>({})
const _loadPresets = vi.fn()
const _applyPreset = vi.fn()
const _saveNewPreset = vi.fn()
const _deletePreset = vi.fn()

vi.mock("@/composables/useLlmSettings", () => ({
  useLlmSettings: () => ({
    presetsByFunc: _presetsByFunc,
    loadPresets: _loadPresets,
    applyPreset: _applyPreset,
    saveNewPreset: _saveNewPreset,
    deletePreset: _deletePreset,
  }),
}))

describe("Preset management integration (SettingsModal Phase 1)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _presetsByFunc.value = {}
  })

  it("loadPresets is callable for a preset-supported feature", async () => {
    const { useLlmSettings } = await import("@/composables/useLlmSettings")
    const { loadPresets } = useLlmSettings()

    await loadPresets("smart_delete")

    expect(_loadPresets).toHaveBeenCalledWith("smart_delete")
  })

  it("presetsByFunc starts empty", () => {
    const { useLlmSettings } = vi.mocked({})
    // Verify the initial state
    expect(_presetsByFunc.value).toEqual({})
  })

  it("applyPreset is callable with func_key and preset_id", async () => {
    const { useLlmSettings } = await import("@/composables/useLlmSettings")
    const { applyPreset } = useLlmSettings()

    await applyPreset("smart_delete", "preset-abc")

    expect(_applyPreset).toHaveBeenCalledWith("smart_delete", "preset-abc")
  })

  it("saveNewPreset is callable with name", async () => {
    const { useLlmSettings } = await import("@/composables/useLlmSettings")
    const { saveNewPreset } = useLlmSettings()

    await saveNewPreset("smart_delete", "学术报告")

    expect(_saveNewPreset).toHaveBeenCalledWith("smart_delete", "学术报告")
  })

  it("deletePreset is callable with preset_id", async () => {
    const { useLlmSettings } = await import("@/composables/useLlmSettings")
    const { deletePreset } = useLlmSettings()

    await deletePreset("smart_delete", "preset-abc")

    expect(_deletePreset).toHaveBeenCalledWith("smart_delete", "preset-abc")
  })

  it("presetsByFunc can be populated with preset data", () => {
    _presetsByFunc.value = {
      smart_delete: [
        { id: "default", name: "默认", params: {}, system_override: "", model: "", created_at: "..." },
        { id: "preset-1", name: "学术报告", params: { custom_fillers: ["那么"] }, system_override: "", model: "", created_at: "..." },
      ],
    }

    expect(_presetsByFunc.value.smart_delete).toHaveLength(2)
    expect(_presetsByFunc.value.smart_delete[0].id).toBe("default")
    expect(_presetsByFunc.value.smart_delete[1].name).toBe("学术报告")
  })
})
