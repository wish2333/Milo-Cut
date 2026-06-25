<script setup lang="ts">
/**
 * P1 Subtitle Correction Review Panel.
 *
 * Shows LLM subtitle corrections in a git-diff-like interface.
 * Users can accept/reject individual corrections, or batch-accept
 * all high-confidence corrections via "trust this source".
 */
import { computed, ref } from "vue"
import type { Segment } from "@/types/project"
import { formatTimeShort } from "@/utils/format"

interface CorrectionItem {
  segment_id: string
  corrected_text: string
  changes: string[]
  category: string
  confidence: number
}

const props = defineProps<{
  corrections: CorrectionItem[]
  segments: Segment[]
  loading?: boolean
  progress?: number
  error?: string | null
  uncoveredIds?: string[]
  partial?: boolean
  llmConfigured: boolean
}>()

const emit = defineEmits<{
  "start-correction": [referenceText: string]
  cancel: []
  "correction-applied": []
  seek: [time: number]
}>()

// Reference text input (mode B)
const referenceText = ref("")

// Track which corrections have been accepted/rejected
const acceptedIds = ref<Set<string>>(new Set())
const rejectedIds = ref<Set<string>>(new Set())

// Segment lookup map
const segmentMap = computed(() => {
  const m = new Map<string, Segment>()
  for (const s of props.segments) {
    m.set(s.id, s)
  }
  return m
})

interface DisplayItem {
  correction: CorrectionItem
  segment: Segment | undefined
  startTime: number
  originalText: string
  correctedText: string
  isLowConfidence: boolean
  isAccepted: boolean
  isRejected: boolean
}

const sortedItems = computed<DisplayItem[]>(() => {
  return props.corrections
    .map((c) => {
      const seg = segmentMap.value.get(c.segment_id)
      const originalText = seg?.text?.trim() ?? ""
      const correctedText = c.corrected_text.trim()
      // Low confidence: either marked by backend or text unchanged
      const noChange = originalText === correctedText
      return {
        correction: c,
        segment: seg,
        startTime: seg?.start ?? 0,
        originalText,
        correctedText,
        isLowConfidence: c.confidence < 0.5 || noChange,
        isAccepted: acceptedIds.value.has(c.segment_id),
        isRejected: rejectedIds.value.has(c.segment_id),
      }
    })
    .sort((a, b) => a.startTime - b.startTime)
})

// Filter out "none" category (no changes needed)
const effectiveItems = computed(() =>
  sortedItems.value.filter(
    (i) => i.correction.category !== "none" && i.originalText !== i.correctedText,
  ),
)

const highConfidenceItems = computed(() =>
  effectiveItems.value.filter((i) => !i.isLowConfidence),
)

const lowConfidenceItems = computed(() =>
  effectiveItems.value.filter((i) => i.isLowConfidence),
)

const pendingCount = computed(
  () =>
    effectiveItems.value.length -
    acceptedIds.value.size -
    rejectedIds.value.size,
)

function categoryLabel(category: string): string {
  const labels: Record<string, string> = {
    homophone: "同音错字",
    proper_noun: "专有名词",
    punctuation: "标点断句",
    reference_aligned: "参考稿对齐",
    none: "无变更",
  }
  return labels[category] ?? category
}

function categoryClass(category: string): string {
  const classes: Record<string, string> = {
    homophone: "badge-warning",
    proper_noun: "badge-info",
    punctuation: "badge-ghost",
    reference_aligned: "badge-success",
    none: "badge-ghost",
  }
  return classes[category] ?? "badge-ghost"
}

function confidenceLabel(conf: number): string {
  if (conf >= 0.8) return "高置信度"
  if (conf >= 0.5) return "中置信度"
  return "低置信度"
}

function accept(id: string) {
  acceptedIds.value.add(id)
  rejectedIds.value.delete(id)
}

function reject(id: string) {
  rejectedIds.value.add(id)
  acceptedIds.value.delete(id)
}

async function acceptAllHighConfidence() {
  for (const item of highConfidenceItems.value) {
    accept(item.correction.segment_id)
  }
  await applyCorrections()
}

async function applyCorrections() {
  const accepted = effectiveItems.value.filter((i) =>
    acceptedIds.value.has(i.correction.segment_id),
  )
  if (accepted.length === 0) return

  // The corrections are already applied by the backend on task completion;
  // this is for re-applying after user edits. For now, just emit.
  emit("correction-applied")
}

function startAnalysis() {
  emit("start-correction", referenceText.value)
}

function handleSeek(time: number) {
  emit("seek", time)
}
</script>

<template>
  <div class="flex h-full flex-col gap-3 overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-semibold text-base-content/80">字幕修正</h3>
      <span v-if="effectiveItems.length > 0" class="text-xs text-base-content/50">
        {{ effectiveItems.length }} 条修正 · {{ pendingCount }} 待审阅
      </span>
    </div>

    <!-- Not configured warning -->
    <div v-if="!llmConfigured" class="alert alert-warning text-xs">
      <span>请先在设置中配置 LLM 连接</span>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-error text-xs">
      <span>{{ error }}</span>
    </div>

    <!-- Loading progress -->
    <div v-if="loading" class="flex flex-col gap-2">
      <progress
        class="progress progress-primary w-full"
        :value="progress ?? 0"
        max="100"
      ></progress>
      <p class="text-center text-xs text-base-content/50">正在分析字幕...</p>
    </div>

    <!-- Uncovered warning -->
    <div v-if="partial && uncoveredIds && uncoveredIds.length > 0" class="alert alert-info text-xs">
      <span>{{ uncoveredIds.length }} 个片段未被修正覆盖（LLM 输出不完整）</span>
    </div>

    <!-- Input area (only when idle) -->
    <div
      v-if="!loading && effectiveItems.length === 0 && llmConfigured"
      class="flex flex-col gap-2"
    >
      <textarea
        v-model="referenceText"
        class="textarea textarea-bordered h-20 text-xs"
        placeholder="参考稿（可选，模式 B）-- 留空使用 LLM 自主纠错（模式 A）"
      ></textarea>
      <button class="btn btn-primary btn-sm" @click="startAnalysis">
        开始字幕修正
      </button>
    </div>

    <!-- Action bar (when results available) -->
    <div
      v-if="effectiveItems.length > 0 && !loading"
      class="flex items-center gap-2"
    >
      <button
        class="btn btn-success btn-xs"
        :disabled="highConfidenceItems.length === 0"
        @click="acceptAllHighConfidence"
      >
        信任高置信度 ({{ highConfidenceItems.length }})
      </button>
      <button class="btn btn-ghost btn-xs" @click="startAnalysis">
        重新分析
      </button>
    </div>

    <!-- Correction list -->
    <div
      v-if="effectiveItems.length > 0"
      class="flex-1 overflow-y-auto pr-1"
    >
      <!-- High confidence section -->
      <div v-if="highConfidenceItems.length > 0" class="mb-3">
        <div class="mb-1 text-xs font-semibold text-success/70">
          高置信度修正 ({{ highConfidenceItems.length }})
        </div>
        <div
          v-for="item in highConfidenceItems"
          :key="item.correction.segment_id"
          class="mb-2 rounded-lg border border-base-300 bg-base-100 p-2 text-xs"
          :class="{
            'opacity-50': item.isRejected,
            'ring-1 ring-success/30': item.isAccepted,
          }"
        >
          <!-- Segment header -->
          <div class="mb-1 flex items-center gap-2">
            <button
              class="link link-hover text-base-content/60"
              @click="handleSeek(item.startTime)"
            >
              {{ formatTimeShort(item.startTime) }}
            </button>
            <span class="badge badge-sm" :class="categoryClass(item.correction.category)">
              {{ categoryLabel(item.correction.category) }}
            </span>
            <span class="text-base-content/40">{{ confidenceLabel(item.correction.confidence) }}</span>
          </div>

          <!-- Diff view -->
          <div class="grid grid-cols-2 gap-1">
            <div class="rounded bg-error/10 p-1 text-error/80 line-through">
              {{ item.originalText }}
            </div>
            <div class="rounded bg-success/10 p-1 text-success/80">
              {{ item.correctedText }}
            </div>
          </div>

          <!-- Changes -->
          <div v-if="item.correction.changes.length > 0" class="mt-1 text-base-content/40">
            {{ item.correction.changes.join("; ") }}
          </div>

          <!-- Actions -->
          <div class="mt-1 flex gap-1" v-if="!item.isAccepted && !item.isRejected">
            <button class="btn btn-success btn-xs" @click="accept(item.correction.segment_id)">
              接受
            </button>
            <button class="btn btn-ghost btn-xs" @click="reject(item.correction.segment_id)">
              拒绝
            </button>
          </div>
          <div v-else class="mt-1 text-xs text-base-content/40">
            {{ item.isAccepted ? "已接受" : "已拒绝" }}
          </div>
        </div>
      </div>

      <!-- Low confidence section (collapsed by default) -->
      <div v-if="lowConfidenceItems.length > 0" class="collapse collapse-arrow">
        <input type="checkbox" />
        <div class="collapse-title text-xs font-semibold text-warning/70">
          低置信度修正 ({{ lowConfidenceItems.length }}) -- 需手动确认
        </div>
        <div class="collapse-content">
          <div
            v-for="item in lowConfidenceItems"
            :key="item.correction.segment_id"
            class="mb-2 rounded-lg border border-warning/20 bg-warning/5 p-2 text-xs"
            :class="{
              'opacity-50': item.isRejected,
              'ring-1 ring-success/30': item.isAccepted,
            }"
          >
            <div class="mb-1 flex items-center gap-2">
              <button
                class="link link-hover text-base-content/60"
                @click="handleSeek(item.startTime)"
              >
                {{ formatTimeShort(item.startTime) }}
              </button>
              <span class="badge badge-sm badge-warning">低置信度</span>
              <span class="badge badge-sm" :class="categoryClass(item.correction.category)">
                {{ categoryLabel(item.correction.category) }}
              </span>
            </div>
            <div class="grid grid-cols-2 gap-1">
              <div class="rounded bg-error/10 p-1 text-error/80 line-through">
                {{ item.originalText }}
              </div>
              <div class="rounded bg-success/10 p-1 text-success/80">
                {{ item.correctedText }}
              </div>
            </div>
            <div class="mt-1 flex gap-1" v-if="!item.isAccepted && !item.isRejected">
              <button class="btn btn-success btn-xs" @click="accept(item.correction.segment_id)">
                接受
              </button>
              <button class="btn btn-ghost btn-xs" @click="reject(item.correction.segment_id)">
                拒绝
              </button>
            </div>
            <div v-else class="mt-1 text-xs text-base-content/40">
              {{ item.isAccepted ? "已接受" : "已拒绝" }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
