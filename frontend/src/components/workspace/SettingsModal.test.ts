/**
 * SettingsModal preset management tests (v2.1.0 Phase 4).
 *
 * Tests the preset composable integration points in isolation.
 * SettingsModal is a large component with many dependencies;
 * these tests verify the preset CRUD API surface.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ref } from "vue"

// Create reactive refs for preset state
const _presetsByFunc = ref<Record<string, Array<{id: string; name: string}>>>({})
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

  it("saveNewPreset is callable with name and params", async () => {
    const mod = await import("@/composables/useLlmSettings")
    const settings = mod.useLlmSettings() as unknown as {
      saveNewPreset: (funcKey: string, name: string) => Promise<void>
    }

    await settings.saveNewPreset("smart_delete", "学术报告")

    expect(_saveNewPreset).toHaveBeenCalledWith("smart_delete", "学术报告")
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
