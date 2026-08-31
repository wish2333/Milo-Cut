<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"
import GeneralSettingsTab from "./settings/GeneralSettingsTab.vue"
import AiEngineSettingsTab from "./settings/AiEngineSettingsTab.vue"
import LlmSettingsTab from "./settings/LlmSettingsTab.vue"
import ExportSettingsTab from "./settings/ExportSettingsTab.vue"
import ShortcutsSettingsTab from "./settings/ShortcutsSettingsTab.vue"

/**
 * Settings modal shell (v3.0.0 M8-1).
 *
 * After the M8-1 split this component only owns: modal chrome (ESC/close),
 * tab switching, settings load (`get_settings`) and save (`handleSave`),
 * plus the shared footer status. Each tab lives in `settings/` and
 * communicates via props down (`settings`, `saving`) / events up
 * (`update` patch, `status` footer message, `busy` save-state). Tab
 * components mount lazily via `v-if`, so inactive tabs hold zero state.
 */
const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

// Phase 4: ESC key closes the fullscreen overlay (D-09 UX)
function handleEsc(e: KeyboardEvent) {
  if (e.key === "Escape" && props.visible) emit("close")
}
onMounted(() => window.addEventListener("keydown", handleEsc))
onUnmounted(() => window.removeEventListener("keydown", handleEsc))

const settings = ref<AppSettings | null>(null)
const saving = ref(false)
const statusMsg = ref("")
const activeTab = ref<"general" | "ai-engine" | "llm" | "export" | "shortcuts">("general")

onMounted(async () => {
  const res = await call<AppSettings>("get_settings")
  if (res.success && res.data) {
    settings.value = res.data
  }
})

async function handleSave() {
  if (!settings.value) return
  saving.value = true
  statusMsg.value = ""
  const res = await call<AppSettings>("update_settings", settings.value)
  saving.value = false
  if (res.success) {
    statusMsg.value = "Settings saved"
    setTimeout(() => { statusMsg.value = "" }, 2000)
  } else {
    statusMsg.value = "Save failed"
  }
  return res.success
}

// Tab events: settings patches, footer status, save-busy mirroring
function handleTabUpdate(patch: Partial<AppSettings>) {
  if (settings.value) {
    settings.value = { ...settings.value, ...patch }
  }
}

function handleTabStatus(message: string, timeout: number) {
  statusMsg.value = message
  if (timeout > 0) setTimeout(() => { statusMsg.value = "" }, timeout)
}

function handleTabBusy(value: boolean) {
  saving.value = value
}
</script>

<template>
  <Teleport to="body">
    <Transition name="overlay-fade">
  <div
    v-if="visible"
    class="fixed inset-0 z-modal bg-white"
  >
    <div class="flex h-full flex-col">
      <div class="flex items-center justify-between px-8 py-4 border-b border-gray-100">
        <h2 class="text-lg font-semibold text-gray-800">设置</h2>
        <button
          class="text-gray-400 hover:text-gray-600 transition-colors"
          title="关闭 (ESC)"
          @click="emit('close')"
        >
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-8 py-6">
        <!-- Tab Navigation -->
        <div role="tablist" class="flex gap-1 border-b border-gray-200 mb-4">
          <button
            v-for="tab in [
              { id: 'general' as const, label: '通用' },
              { id: 'ai-engine' as const, label: 'AI 引擎' },
              { id: 'llm' as const, label: 'LLM' },
              { id: 'export' as const, label: '导出' },
              { id: 'shortcuts' as const, label: '快捷键' },
            ]"
            :key="tab.id"
            role="tab"
            :aria-selected="activeTab === tab.id"
            class="px-4 py-2 text-sm font-medium transition-colors -mb-px border-b-2"
            :class="activeTab === tab.id
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- Tab 1: General -->
        <GeneralSettingsTab
          v-if="activeTab === 'general' && settings"
          :settings="settings"
          @update="handleTabUpdate"
          @status="handleTabStatus"
        />

        <!-- Tab 2: AI Engine -->
        <AiEngineSettingsTab
          v-if="activeTab === 'ai-engine' && settings"
          :settings="settings"
          @update="handleTabUpdate"
          @status="handleTabStatus"
        />

        <!-- Tab 3: LLM -->
        <LlmSettingsTab
          v-if="activeTab === 'llm' && settings"
          :settings="settings"
          :saving="saving"
          @update="handleTabUpdate"
          @status="handleTabStatus"
          @busy="handleTabBusy"
        />

        <!-- Tab 4: Export -->
        <ExportSettingsTab
          v-if="activeTab === 'export' && settings"
          :settings="settings"
          @update="handleTabUpdate"
        />

        <!-- Tab 5: Shortcuts -->
        <ShortcutsSettingsTab v-if="activeTab === 'shortcuts'" />
      </div>

      <div class="px-8 py-4 border-t border-gray-100 flex items-center justify-between">
        <span class="text-sm text-gray-500">{{ statusMsg }}</span>
        <div class="flex gap-2">
          <button
            class="px-4 py-2 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
            @click="emit('close')"
          >
            关闭
          </button>
          <button
            class="px-4 py-2 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 active:scale-95 disabled:opacity-50 transition-all duration-150"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? "保存中..." : "保存" }}
          </button>
        </div>
      </div>
    </div>
  </div>
    </Transition>
  </Teleport>
</template>

<style>
/* Phase 4: 全屏覆盖层淡入淡出 -- 150ms 平滑过渡,避免突兀的白板闪现 */
.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 150ms ease;
}
.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}
</style>
