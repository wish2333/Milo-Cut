<script setup lang="ts">
/**
 * AI Assistant Panel (Phase 2 D-02, D-04, D-12, D-14).
 *
 * Central entry point for all LLM-powered features:
 *   - 快速清理 (智能删除 P0): launches analysis, results merge into
 *     SuggestionPanel as the "llm_smart" group (D-15).
 *   - 字幕纠错 (字幕修正 P1): launches analysis, then shows a "view
 *     results" button that opens the fullscreen diff view (D-16).
 *   - 内容搜索 (语义搜索 P3): inline SemanticSearchBar (D-02).
 *
 * Feature cards show 场景名 (primary) + 功能名 (subtitle) per D-14.
 * When LLM is not configured, cards are greyed out per D-12.
 */
import { computed, onMounted, ref, watch } from "vue"
import SemanticSearchBar from "@/components/workspace/SemanticSearchBar.vue"
import { useWorkflow } from "@/composables/useWorkflow"
import type { WorkflowStep } from "@/composables/useWorkflow"
import type { Segment } from "@/types/project"
import { useLlmSettings } from "@/composables/useLlmSettings"

type FeatureKey = "smart_delete" | "subtitle_correction" | "search"
type PanelMode = "single" | "workflow"

const props = defineProps<{
  segments: Segment[]
  llmConfigured: boolean
  llmModel: string
  isRunning: boolean
  progress: number
  errorMsg: string | null
  // P1 subtitle correction result count (null = not run yet)
  subtitleCorrectionCount: number | null
}>()

const emit = defineEmits<{
  "start-smart-delete": []
  "switch-to-suggestion": []
  "start-subtitle-correction": [referenceText: string]
  "open-subtitle-fullscreen": []
  "go-to-settings": []
  seek: [time: number]
  "cancel-single": []
}>()

// v2.1.0 Phase 3: workflow composable
const wf = useWorkflow()
// v2.1.0 Phase 4: preset loading for workflow steps (D-43)
const llmSettings = useLlmSettings()

// Step type -> preset func_key mapping (D-43)
const STEP_TO_PRESET_KEY: Record<string, string> = {
  llm_smart_delete: "smart_delete",
  llm_subtitle_correction: "subtitle_correction_a",
  llm_highlight: "highlight",
  // Single-function mode keys
  smart_delete: "smart_delete",
  subtitle_correction: "subtitle_correction_a",
}

const panelMode = ref<PanelMode>("single")
const selectedFeature = ref<FeatureKey | null>(null)
const referenceText = ref("")
const currentPresetId = ref("")           // shared preset for single-function ops

// Workflow config state
const newWorkflowName = ref("")
const newWorkflowSteps = ref<WorkflowStep[]>([
  { type: "llm_smart_delete", preset_id: null },
  { type: "llm_subtitle_correction", preset_id: null },
])
const selectedWorkflowId = ref("")
const autoSavedWorkflowId = ref("") // v2.2.1: track auto-saved workflows for cleanup

const stepLabels: Record<string, string> = {
  llm_smart_delete: "P0 智能删除",
  llm_subtitle_correction: "P1 字幕修正",
  llm_highlight: "P2 精华提取",
}

const availableSteps = [
  { type: "llm_smart_delete" as const, label: "P0 智能删除" },
  { type: "llm_subtitle_correction" as const, label: "P1 字幕修正" },
  { type: "llm_highlight" as const, label: "P2 精华提取" },
]

// Preset options per step type (D-43)
const stepPresetOptions = ref<Record<string, Array<{id: string; name: string}>>>({})

function getPresetKey(stepType: string): string | null {
  return STEP_TO_PRESET_KEY[stepType] || null
}

async function loadStepPresets(stepType: string) {
  const funcKey = getPresetKey(stepType)
  if (!funcKey) return
  await llmSettings.loadPresets(funcKey)
  const presets = llmSettings.presetsByFunc.value[funcKey] || []
  stepPresetOptions.value = {
    ...stepPresetOptions.value,
    [stepType]: presets.map((p) => ({ id: p.id, name: p.name })),
  }
}

function getStepPresetId(stepType: string): string {
  const step = newWorkflowSteps.value.find((s) => s.type === stepType)
  return step?.preset_id || ""
}

function setStepPresetId(stepType: string, presetId: string) {
  const step = newWorkflowSteps.value.find((s) => s.type === stepType)
  if (step) {
    step.preset_id = presetId || null
  }
}

interface FeatureCard {
  key: FeatureKey
  title: string
  subtitle: string
  description: string
  icon: string
}

const features: FeatureCard[] = [
  {
    key: "smart_delete",
    title: "快速清理",
    subtitle: "智能删除",
    description: "AI 自动识别口头禅、重复、口误等可删片段",
    icon: "M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16",
  },
  {
    key: "subtitle_correction",
    title: "字幕纠错",
    subtitle: "字幕修正",
    description: "AI 修正同音错字、专有名词、标点断句",
    icon: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
  },
  {
    key: "search",
    title: "内容搜索",
    subtitle: "语义搜索",
    description: "用自然语言查找视频中的相关片段",
    icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  },
]

const hasCorrectionResults = computed(
  () => props.subtitleCorrectionCount !== null && props.subtitleCorrectionCount > 0,
)

function selectFeature(key: FeatureKey) {
  if (!props.llmConfigured) return
  selectedFeature.value = selectedFeature.value === key ? null : key
}

// Workflow helpers
function toggleStep(stepType: WorkflowStep["type"]) {
  const idx = newWorkflowSteps.value.findIndex((s) => s.type === stepType)
  if (idx >= 0) {
    newWorkflowSteps.value.splice(idx, 1)
  } else {
    newWorkflowSteps.value.push({ type: stepType, preset_id: null })
    // Load presets for this step type (D-43)
    loadStepPresets(stepType)
  }
}

function isStepChecked(stepType: WorkflowStep["type"]) {
  return newWorkflowSteps.value.some((s) => s.type === stepType)
}

/** Returns 1-based execution order for a checked step, or 0 if unchecked. */
function getStepOrder(stepType: WorkflowStep["type"]): number {
  return newWorkflowSteps.value.findIndex((s) => s.type === stepType) + 1
}

async function handleSaveWorkflow() {
  if (!newWorkflowName.value.trim()) return
  const steps = newWorkflowSteps.value
  if (steps.length === 0) return
  const res = await wf.saveWorkflow(newWorkflowName.value, steps)
  if (res.success) {
    newWorkflowName.value = ""
    selectedWorkflowId.value = res.data?.id || ""
  }
}

async function handleStartWorkflow() {
  if (newWorkflowSteps.value.length === 0) return

  // Auto-save before start if no workflow selected
  if (!selectedWorkflowId.value) {
    const name = newWorkflowName.value.trim() || `工作流 ${new Date().toLocaleTimeString()}`
    const res = await wf.saveWorkflow(name, newWorkflowSteps.value)
    if (!res.success) {
      return
    }
    autoSavedWorkflowId.value = res.data?.id || ""
    selectedWorkflowId.value = res.data?.id || ""
    newWorkflowName.value = name
  }

  await wf.startWorkflow(selectedWorkflowId.value)
}

async function handleDeleteWorkflow() {
  if (!selectedWorkflowId.value) return
  await wf.deleteWorkflow(selectedWorkflowId.value)
  selectedWorkflowId.value = ""
}

async function handleCancelWorkflow(mode: "immediate" | "after_current") {
  await wf.cancelWorkflow(mode)
}

// v2.2.0: 非沙箱模式 — 工作流步骤已直接写入 project，完成后仅提供「返回配置」
function handleReturnToConfig() {
  // 清除 instanceId，回到配置视图（v-else 分支）
  wf.instanceId.value = null
}

// v2.2.1: 自动清理无配置启动时自动保存的工作流
watch(() => wf.isActive.value, (newVal, oldVal) => {
  if (!newVal && oldVal && autoSavedWorkflowId.value) {
    const id = autoSavedWorkflowId.value
    autoSavedWorkflowId.value = ""
    wf.deleteWorkflow(id)
  }
})

onMounted(() => {
  wf.loadWorkflows()
  // Load presets for ALL available workflow step types so their config
  // dropdowns appear immediately (even for unchecked steps).
  availableSteps.forEach((s) => loadStepPresets(s.type))
  // Load presets for single-function mode (smart_delete + subtitle_correction)
  loadStepPresets("smart_delete")
  loadStepPresets("subtitle_correction")
})

// When user selects a saved workflow from the dropdown, populate the step checkboxes
// so they can see/verify the steps before launching.
watch(selectedWorkflowId, (id) => {
  if (!id) return
  const saved = wf.workflows.value.find((w) => w.id === id)
  if (!saved) return
  // Replace newWorkflowSteps with the saved workflow's steps,
  // preserving the order from the saved definition.
  newWorkflowSteps.value = saved.steps.map((s) => ({
    type: s.type,
    preset_id: s.preset_id ?? null,
  }))
  // Also fill the workflow name field
  newWorkflowName.value = saved.name
  // Load presets for each step
  saved.steps.forEach((s) => loadStepPresets(s.type))
})

async function handleStartSmartDelete() {
  emit("start-smart-delete")
}

function handleStartSubtitleCorrection() {
  emit("start-subtitle-correction", referenceText.value)
}

function handleCancelSingle() {
  emit("cancel-single")
}

function handleOpenFullscreen() {
  emit("open-subtitle-fullscreen")
}

function handleSearchSeek(time: number) {
  emit("seek", time)
}
</script>

<template>
  <div class="flex h-full flex-col gap-3 overflow-hidden">
    <!-- LLM status indicator (D-04) -->
    <div class="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2">
      <div class="flex items-center gap-2">
        <span
          class="inline-block h-2 w-2 rounded-full"
          :class="llmConfigured ? 'bg-green-500' : 'bg-amber-500'"
        ></span>
        <span class="text-xs font-medium" :class="llmConfigured ? 'text-gray-700' : 'text-amber-700'">
          {{ llmConfigured ? `LLM 已配置` : `未配置` }}
        </span>
        <span v-if="llmConfigured && llmModel" class="text-xs text-gray-500 truncate max-w-[120px]">
          {{ llmModel }}
        </span>
      </div>
      <button
        v-if="!llmConfigured"
        class="text-xs text-blue-600 hover:text-blue-800 underline"
        @click="emit('go-to-settings')"
      >
        去设置
      </button>
    </div>

    <!-- Error message -->
    <div v-if="errorMsg" class="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
      {{ errorMsg }}
    </div>

    <!-- Workflow error message -->
    <div v-if="wf.errorMsg.value" class="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
      {{ wf.errorMsg.value }}
    </div>

    <!-- Mode switch (D-19) -->
    <div class="flex gap-1 rounded-lg bg-gray-100 p-0.5">
      <button
        class="flex-1 rounded-md px-3 py-1 text-xs font-medium transition-colors"
        :class="panelMode === 'single' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'"
        @click="panelMode = 'single'"
      >单功能</button>
      <button
        class="flex-1 rounded-md px-3 py-1 text-xs font-medium transition-colors"
        :class="panelMode === 'workflow' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'"
        @click="panelMode = 'workflow'"
      >工作流</button>
    </div>

    <!-- ============ Workflow Mode (Phase 3) ============ -->
    <template v-if="panelMode === 'workflow'">
      <!-- Execution view (when active or completed pending review) -->
      <div v-if="wf.isActive.value || wf.instanceId.value" class="flex flex-col gap-3">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-gray-700">
            {{ wf.workflowName.value }}
          </span>
          <span v-if="wf.cancelMode.value === 'after_current'" class="text-xs text-amber-600">
            Cancelling...
          </span>
        </div>

        <!-- Overall progress (D-20) -->
        <div class="flex flex-col gap-1">
          <div class="flex justify-between text-xs text-gray-500">
            <span>总进度</span>
            <span>{{ wf.currentStepIndex.value }}/{{ wf.totalSteps.value }}</span>
          </div>
          <div class="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
            <div
              class="h-full bg-blue-500 transition-all duration-300"
              :style="{ width: `${wf.overallProgress.value}%` }"
            ></div>
          </div>
        </div>

        <!-- Step list (D-70: queued/running/pending distinction) -->
        <div class="flex flex-col gap-1.5">
          <div
            v-for="step in wf.stepResults.value"
            :key="step.index"
            class="flex items-center gap-2 rounded-md px-2 py-1 text-xs"
            :class="{
              'bg-green-50 text-green-700': step.status === 'completed',
              'bg-blue-50 text-blue-700': step.status === 'running',
              'bg-gray-50 text-gray-400': step.status === 'pending',
            }"
          >
            <span v-if="step.status === 'completed'">&#10003;</span>
            <span v-else-if="step.status === 'running'" class="animate-pulse">&#9679;</span>
            <span v-else-if="step.status === 'queued'" class="text-amber-500">&#9203;</span>
            <span v-else>&#9675;</span>
            <span>{{ stepLabels[step.type] || step.type }}</span>
            <span v-if="step.status === 'running' && wf.stepProgress.value[step.index]" class="ml-auto text-gray-400">
              {{ Math.round(wf.stepProgress.value[step.index].percent) }}%
            </span>
            <span v-else-if="step.status === 'completed'" class="ml-auto">
              {{ step.edits_count }} 条
            </span>
            <span v-else-if="step.status === 'queued'" class="ml-auto text-amber-500">
              等待系统资源...
            </span>
          </div>
        </div>

        <!-- Cancel buttons (D-22) -->
        <div v-if="wf.isActive.value && !wf.cancelMode.value" class="flex gap-2">
          <button
            class="flex-1 rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
            @click="handleCancelWorkflow('immediate')"
          >立即取消</button>
          <button
            class="flex-1 rounded-md border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-600 hover:bg-amber-50"
            @click="handleCancelWorkflow('after_current')"
          >当前步骤后停</button>
        </div>
        <button
          v-else-if="wf.cancelMode.value === 'after_current'"
          class="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
          @click="handleCancelWorkflow('immediate')"
        >立即取消 (不等待)</button>

        <!-- D-11: Step failure dialog -->
        <Teleport to="body">
          <div
            v-if="wf.showFailureDialog.value && wf.failureInfo.value"
            class="fixed inset-0 z-modal flex items-center justify-center bg-black/40"
          >
            <div class="w-[360px] rounded-xl bg-white p-5 shadow-xl">
              <h3 class="mb-1 text-sm font-semibold text-gray-800">步骤执行失败</h3>
              <p class="mb-1 text-xs text-gray-500">
                {{ wf.failureInfo.value?.stepName || "未知步骤" }}
              </p>
              <p class="mb-4 text-xs text-red-600">
                {{ wf.failureInfo.value?.error || "未知错误" }}
              </p>
              <div class="flex gap-2">
                <button
                  class="flex-1 rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600"
                  @click="wf.handleStepFailure('retry')"
                >重试</button>
                <button
                  class="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                  @click="wf.handleStepFailure('skip')"
                >跳过</button>
                <button
                  class="flex-1 rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
                  @click="wf.handleStepFailure('abort')"
                >中止</button>
              </div>
              <!-- v3.0.0 M3-6: optional failure rollback (undo layers) -->
              <div class="mt-2 flex gap-2">
                <button
                  class="flex-1 rounded-md border border-amber-400 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50"
                  title="撤销本步骤已写入的变更（保留之前步骤的效果），然后结束工作流"
                  @click="wf.handleStepFailure('rollback_step')"
                >回滚本步</button>
                <button
                  class="flex-1 rounded-md border border-amber-400 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50"
                  title="撤销工作流开始以来的全部变更，然后结束工作流"
                  @click="wf.handleStepFailure('rollback_all')"
                >全部回滚</button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- v2.2.0: 完成状态视图 — 移除 Apply/Discard，改为「返回配置」 -->
        <div v-if="!wf.isActive.value && wf.instanceId.value" class="flex flex-col gap-2">
          <div class="rounded-md bg-green-50 px-3 py-2 text-xs text-green-700">
            工作流已完成 — 结果已写入项目
          </div>
          <button
            class="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
            @click="handleReturnToConfig"
          >返回配置</button>
        </div>
      </div>

      <!-- Config view (when not active and no instance) -->
      <div v-else class="flex flex-1 flex-col gap-3 overflow-y-auto">
        <!-- Big "启动" button at top -->
        <button
          class="w-full rounded-md bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          :disabled="newWorkflowSteps.length === 0"
          @click="handleStartWorkflow"
        >工作流启动</button>

        <!-- Saved workflow select + save + delete in one row -->
        <div class="flex items-center gap-2">
          <select
            v-model="selectedWorkflowId"
            class="flex-1 rounded-md border border-gray-200 px-2 py-1.5 text-xs"
          >
            <option value="">-- 选择已保存工作流 --</option>
            <option v-for="w in wf.workflows.value" :key="w.id" :value="w.id">
              {{ w.name }} ({{ w.steps.length }} 步)
            </option>
          </select>
          <button
            class="shrink-0 rounded-md bg-gray-700 px-2 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            :disabled="!newWorkflowName.trim() || newWorkflowSteps.length === 0"
            @click="handleSaveWorkflow"
          >保存</button>
          <button
            class="shrink-0 rounded-md border border-red-300 px-2 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
            :disabled="!selectedWorkflowId"
            @click="handleDeleteWorkflow"
          >删除</button>
        </div>

        <!-- New workflow name -->
        <input
          v-model="newWorkflowName"
          class="w-full rounded-md border border-gray-200 px-2 py-1.5 text-xs"
          placeholder="工作流名称"
        />

        <!-- Steps checkboxes -->
        <div class="flex flex-col gap-1.5">
          <p class="text-xs text-gray-500">步骤 (按勾选顺序执行):</p>
          <label
            v-for="step in availableSteps"
            :key="step.type"
            class="flex flex-col gap-1 rounded-md border border-gray-100 px-2 py-1.5"
            :class="{ 'bg-blue-50 border-blue-200': isStepChecked(step.type) }"
          >
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                :checked="isStepChecked(step.type)"
                class="h-3.5 w-3.5"
                @change="toggleStep(step.type)"
              />
              <span class="flex-1 text-xs text-gray-700">{{ step.label }}</span>
              <span
                v-if="isStepChecked(step.type)"
                class="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-blue-500 text-[10px] font-bold text-white"
              >{{ getStepOrder(step.type) }}</span>
            </div>
            <!-- D-43: per-step preset picker (always visible if presets exist) -->
            <select
              v-if="stepPresetOptions[step.type]"
              :value="getStepPresetId(step.type)"
              class="w-full rounded border border-gray-200 px-1.5 py-1 text-xs text-gray-600"
              @change="setStepPresetId(step.type, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">(使用当前配置)</option>
              <option
                v-for="p in stepPresetOptions[step.type]"
                :key="p.id"
                :value="p.id"
              >
                {{ p.name }}
              </option>
            </select>
          </label>
        </div>

      </div>
    </template>

    <!-- ============ Single Function Mode (existing) ============ -->
    <template v-else>
    <!-- Progress bar (shared) -->
    <div v-if="isRunning" class="flex items-center gap-2">
      <div class="flex-1">
        <div class="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            class="h-full bg-blue-500 transition-all duration-300"
            :style="{ width: `${progress}%` }"
          ></div>
        </div>
      </div>
      <button
        class="shrink-0 rounded-md border border-red-300 px-2 py-1 text-[10px] font-medium text-red-600 hover:bg-red-50"
        @click="handleCancelSingle"
      >取消</button>
    </div>

    <!-- Feature cards (D-14) -->
    <div class="grid grid-cols-2 gap-2">
      <button
        v-for="feat in features.slice(0, 2)"
        :key="feat.key"
        class="relative flex flex-col items-start rounded-lg border p-2 text-left transition-colors"
        :class="[
          llmConfigured
            ? selectedFeature === feat.key
              ? 'border-blue-400 bg-blue-50'
              : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
            : 'cursor-not-allowed border-gray-200 bg-gray-100 opacity-50',
        ]"
        :disabled="!llmConfigured"
        @click="selectFeature(feat.key)"
      >
        <svg
          v-if="!llmConfigured"
          class="absolute right-1 top-1 h-3 w-3 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <span v-if="!llmConfigured" class="absolute right-1 top-1 text-[10px] text-gray-400">未配置</span>
        <div class="flex items-center gap-1.5">
          <svg
            class="h-4 w-4 text-gray-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path stroke-linecap="round" stroke-linejoin="round" :d="feat.icon" />
          </svg>
          <span class="text-sm font-medium text-gray-800">{{ feat.title }}</span>
        </div>
        <span class="text-xs text-gray-400">({{ feat.subtitle }})</span>
      </button>
    </div>
    <!-- Search card (full-width under grid) -->
    <button
      class="relative flex items-start rounded-lg border p-2 text-left transition-colors"
      :class="[
        llmConfigured
          ? selectedFeature === 'search'
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
          : 'cursor-not-allowed border-gray-200 bg-gray-100 opacity-50',
      ]"
      :disabled="!llmConfigured"
      @click="selectFeature('search')"
    >
      <svg
        v-if="!llmConfigured"
        class="absolute right-1 top-1 h-3 w-3 text-gray-400"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        stroke-width="2"
      >
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
      <span v-if="!llmConfigured" class="absolute right-1 top-1 text-[10px] text-gray-400">未配置</span>
      <div class="flex items-center gap-1.5">
        <svg
          class="h-4 w-4 shrink-0 text-gray-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" :d="features[2].icon" />
        </svg>
        <div class="flex flex-col">
          <span class="text-sm font-medium text-gray-800">内容搜索</span>
          <span class="text-xs text-gray-400">语义搜索</span>
        </div>
      </div>
    </button>

    <!-- Operation area (selected feature detail) -->
    <div v-if="selectedFeature" class="flex flex-1 flex-col gap-2 overflow-y-auto">
      <!-- Smart delete (P0) -->
      <div v-if="selectedFeature === 'smart_delete'" class="flex flex-col gap-2">
        <p class="text-xs text-gray-600">{{ features[0].description }}</p>
        <select
          v-model="currentPresetId"
          class="w-full rounded border border-gray-200 px-1.5 py-1 text-xs text-gray-600"
        >
          <option value="">(使用当前配置)</option>
          <option
            v-for="p in stepPresetOptions['smart_delete'] ?? []"
            :key="p.id"
            :value="p.id"
          >
            {{ p.name }}
          </option>
        </select>
        <button
          class="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50"
          :disabled="isRunning"
          @click="handleStartSmartDelete"
        >
          开始智能分析
        </button>
        <p class="text-xs text-gray-400">
          分析完成后结果将自动合并到「建议」面板的「智能删除」分组
        </p>
      </div>

      <!-- Subtitle correction (P1) -->
      <div v-if="selectedFeature === 'subtitle_correction'" class="flex flex-col gap-2">
        <p class="text-xs text-gray-600">{{ features[1].description }}</p>
        <select
          v-model="currentPresetId"
          class="w-full rounded border border-gray-200 px-1.5 py-1 text-xs text-gray-600"
        >
          <option value="">(使用当前配置)</option>
          <option
            v-for="p in stepPresetOptions['subtitle_correction'] ?? []"
            :key="p.id"
            :value="p.id"
          >
            {{ p.name }}
          </option>
        </select>
        <textarea
          v-model="referenceText"
          class="w-full rounded-md border border-gray-200 p-2 text-xs"
          rows="4"
          placeholder="参考稿（可选，模式 B）-- 留空使用 LLM 自主纠错（模式 A）"
          :disabled="isRunning"
        ></textarea>
        <button
          class="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50"
          :disabled="isRunning"
          @click="handleStartSubtitleCorrection"
        >
          开始字幕修正
        </button>
        <button
          v-if="hasCorrectionResults"
          class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
          @click="handleOpenFullscreen"
        >
          查看修正结果 ({{ subtitleCorrectionCount }} 条)
        </button>
      </div>

      <!-- Semantic search (P3) -->
      <div v-if="selectedFeature === 'search'" class="flex flex-col gap-2">
        <SemanticSearchBar
          :segments="segments"
          :llm-configured="llmConfigured"
          @seek="handleSearchSeek"
        />
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-else
      class="flex flex-1 items-center justify-center text-xs text-gray-400"
    >
      选择一个功能开始
    </div>
    </template>
    <!-- ============ End Single Function Mode ============ -->

  </div>
</template>
