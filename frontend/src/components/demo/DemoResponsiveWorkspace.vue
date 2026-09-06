<script setup lang="ts">
import { computed, ref } from "vue"
import type { EditDecision, Project, Segment } from "@/types/project"
import DemoPreviewSurface from "@/components/demo/DemoPreviewSurface.vue"
import VideoControls from "@/components/workspace/VideoControls.vue"
import { formatTimeShort } from "@/utils/format"

interface Correction {
  id: string
  segment_id: string
  confidence: number
  original_text: string
  corrected_text: string
  category: string
  start: number
  end: number
}

const props = defineProps<{
  project: Project
  currentTime: number
  duration: number
  paused: boolean
  volume: number
  playbackRate: number
  previewMode: "original" | "edited"
  deleteRanges: Array<{ start: number; end: number }>
  llmConfigured: boolean
  llmIsRunning: boolean
  llmProgress: number
  llmErrorMsg: string | null
  corrections: Correction[]
}>()

const emit = defineEmits<{
  "update:current-time": [time: number]
  "update:volume": [volume: number]
  "update:playback-rate": [rate: number]
  "toggle-play": []
  "toggle-preview": []
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "confirm-edit": [editId: string]
  "reject-edit": [editId: string]
  "start-smart-delete": []
  "start-subtitle-correction": [referenceText: string]
  "accept-correction": [id: string]
  "reject-correction": [id: string]
  "start-highlight": [targetMinutes: number]
  "go-to-export": []
  "project-closed": []
}>()

const activeSection = ref<"timeline" | "ai" | "review">("timeline")
const sections = [
  { key: "timeline" as const, label: "时间轴" },
  { key: "ai" as const, label: "AI 工具" },
  { key: "review" as const, label: "建议审阅" },
]
const activeTimeline = computed(() => props.project.timelines.find((timeline) => timeline.id === props.project.active_timeline_id) ?? props.project.timelines[0])
const segments = computed(() => activeTimeline.value?.transcript.segments ?? [])
const subtitles = computed(() => segments.value.filter((segment) => segment.type === "subtitle"))
const currentSubtitle = computed(() => {
  const active = subtitles.value.find((segment) => props.currentTime >= segment.start && props.currentTime <= segment.end)
  if (active) return active
  const first = subtitles.value[0]
  return first && props.currentTime < first.start ? first : undefined
})
const pendingEdits = computed(() => activeTimeline.value?.edits.filter((edit) => edit.status === "pending") ?? [])
const highlights = computed(() => activeTimeline.value?.analysis.results.filter((result) => result.type === "llm_highlight") ?? [])
const confirmedDeleteDuration = computed(() => activeTimeline.value?.edits
  .filter((edit) => edit.action === "delete" && edit.status === "confirmed")
  .reduce((sum, edit) => sum + edit.end - edit.start, 0) ?? 0)

function segmentForEdit(edit: EditDecision): Segment | undefined {
  return segments.value.find((segment) => segment.id === edit.target_id)
}

function editLabel(edit: EditDecision): string {
  if (edit.source === "llm_smart") return "AI 删除建议"
  if (edit.source === "silence_detection") return "静音建议"
  return "时间轴建议"
}

function setSection(key: (typeof sections)[number]["key"]) {
  activeSection.value = key
}

function handleSeekFromRange(event: Event) {
  emit("update:current-time", Number((event.target as HTMLInputElement).value))
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-canvas">
    <header class="shrink-0 border-b border-white/10 bg-surface-tile-1 px-3 py-2.5 text-white sm:px-4">
      <div class="flex items-center gap-2">
        <button class="mc-button mc-button-quiet min-h-8 p-1 text-white/70 hover:bg-white/10 hover:text-white" aria-label="返回项目" @click="emit('project-closed')">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-semibold">{{ project.project.name }}</div>
          <div class="text-[11px] text-white/55">{{ subtitles.length }} 条字幕 · {{ formatTimeShort(duration) }}</div>
        </div>
        <button class="mc-button mc-button-secondary min-h-8 px-2 text-xs" @click="emit('go-to-export')">导出</button>
      </div>
    </header>

    <main class="min-h-0 flex-1 overflow-y-auto pb-16 pt-8">
      <section class="px-3 pb-2 pt-3 sm:px-4">
        <div class="flex h-[min(36vh,360px)] min-h-[210px] w-full items-center justify-center">
          <DemoPreviewSurface
            :segments="segments"
            :current-time="currentTime"
            :duration="duration"
            :preview-mode="previewMode"
            :delete-ranges="deleteRanges"
          />
        </div>
        <VideoControls
          :current-time="currentTime"
          :duration="duration"
          :paused="paused"
          :volume="volume"
          :playback-rate="playbackRate"
          :delete-ranges="deleteRanges"
          :preview-mode="previewMode"
          @update:current-time="emit('update:current-time', $event)"
          @update:volume="emit('update:volume', $event)"
          @update:playback-rate="emit('update:playback-rate', $event)"
          @toggle-play="emit('toggle-play')"
        />
        <div class="mt-1 flex justify-end">
          <button class="mc-button mc-button-quiet min-h-7 px-2 text-[11px]" @click="emit('toggle-preview')">
            {{ previewMode === "edited" ? "切换到原始预览" : "切换到已编辑预览" }}
          </button>
        </div>
        <div class="mt-2 rounded-[var(--radius-control)] bg-parchment px-3 py-2">
          <div class="mb-1 flex items-center justify-between text-[11px] text-ink-muted">
            <span>演示时间轴</span>
            <span>{{ formatTimeShort(currentTime) }} / {{ formatTimeShort(duration) }}</span>
          </div>
          <input class="demo-range w-full accent-primary" type="range" min="0" :max="duration" step="0.1" :value="currentTime" aria-label="演示时间轴" @input="handleSeekFromRange">
          <div class="mt-1 flex h-5 items-end gap-px overflow-hidden opacity-70" aria-hidden="true">
            <i v-for="index in 72" :key="index" class="min-w-0 flex-1 bg-primary" :style="{ height: (20 + ((index * 17) % 70)) + '%' }" />
          </div>
        </div>
        <div class="mt-2 rounded-[var(--radius-control)] border-l-2 border-primary bg-primary-soft px-3 py-2.5">
          <div class="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-primary">当前字幕</div>
          <p class="min-h-10 text-sm font-medium leading-6 text-ink">{{ currentSubtitle?.text || "移动播放头，查看对应字幕" }}</p>
          <div class="mt-2 flex gap-1.5 overflow-x-auto pb-0.5">
            <button
              v-for="segment in subtitles"
              :key="segment.id"
              class="shrink-0 rounded-full border px-2 py-1 text-[10px] transition-colors"
              :class="currentSubtitle?.id === segment.id ? 'border-primary bg-primary text-white' : 'border-hairline bg-canvas text-ink-muted'"
              @click="emit('seek', segment.start)"
            >
              {{ formatTimeShort(segment.start) }}
            </button>
          </div>
        </div>
      </section>

      <section v-if="activeSection === 'timeline'" class="space-y-2 px-3 pb-4 sm:px-4">
        <div class="flex items-center justify-between pt-2">
          <h2 class="text-sm font-semibold text-ink">字幕片段</h2>
          <span class="text-[11px] text-ink-muted">点击时间 · 文本可修改</span>
        </div>
        <article v-for="segment in subtitles" :key="segment.id" class="rounded-[var(--radius-control)] border border-hairline bg-canvas p-3">
          <div class="mb-1.5 flex items-center justify-between gap-2 text-[11px] text-ink-muted">
            <button class="font-medium text-primary" @click="emit('seek', segment.start)">{{ formatTimeShort(segment.start) }} – {{ formatTimeShort(segment.end) }}</button>
            <span v-if="currentTime >= segment.start && currentTime <= segment.end" class="text-primary">播放中</span>
          </div>
          <textarea class="min-h-14 w-full resize-y bg-transparent text-sm leading-6 text-ink outline-none placeholder:text-ink-muted/70" :value="segment.text" aria-label="编辑字幕" @change="emit('update-text', segment.id, ($event.target as HTMLTextAreaElement).value)" />
        </article>
      </section>

      <section v-else-if="activeSection === 'ai'" class="space-y-3 px-3 pb-4 pt-3 sm:px-4">
        <div class="rounded-[var(--radius-control)] bg-parchment p-3">
          <div class="flex items-center justify-between gap-3">
            <div><h2 class="text-sm font-semibold text-ink">AI 演示工具</h2><p class="mt-1 text-xs text-ink-muted">确定性模拟，不会调用外部 API。</p></div>
            <span class="text-[11px] text-primary">{{ llmConfigured ? "已就绪" : "演示模式" }}</span>
          </div>
        </div>
        <button class="mc-button mc-button-primary w-full justify-between" :disabled="llmIsRunning" @click="emit('start-smart-delete')"><span>智能删除</span><span class="text-xs opacity-70">口头禅与停顿</span></button>
        <button class="mc-button mc-button-secondary w-full justify-between" :disabled="llmIsRunning" @click="emit('start-subtitle-correction', '')"><span>字幕纠错</span><span class="text-xs text-ink-muted">{{ corrections.length }} 条待审</span></button>
        <button class="mc-button mc-button-secondary w-full justify-between" :disabled="llmIsRunning" @click="emit('start-highlight', 1)"><span>提取精华</span><span class="text-xs text-ink-muted">{{ highlights.length ? "已有结果" : "开始分析" }}</span></button>
        <div v-if="llmIsRunning" class="rounded-[var(--radius-control)] border border-primary/20 bg-primary-soft p-3 text-xs text-primary">
          <div class="mb-2 flex justify-between"><span>正在运行演示任务</span><span>{{ llmProgress }}%</span></div>
          <div class="h-1 overflow-hidden rounded-full bg-primary/15"><div class="h-full bg-primary transition-[width]" :style="{ width: llmProgress + '%' }" /></div>
        </div>
        <p v-if="llmErrorMsg" class="text-xs text-status-warning">{{ llmErrorMsg }}</p>
      </section>

      <section v-else class="space-y-3 px-3 pb-4 pt-3 sm:px-4">
        <div class="flex items-center justify-between">
          <div><h2 class="text-sm font-semibold text-ink">建议与审阅</h2><p class="mt-1 text-xs text-ink-muted">确认前不会改变导出结果。</p></div>
        </div>
        <div v-if="pendingEdits.length === 0 && corrections.length === 0" class="rounded-[var(--radius-control)] bg-parchment p-4 text-center text-xs text-ink-muted">暂无待处理建议</div>
        <article v-for="edit in pendingEdits" :key="edit.id" class="rounded-[var(--radius-control)] border border-hairline bg-canvas p-3">
          <div class="flex items-start justify-between gap-2"><div><div class="text-xs font-semibold text-ink">{{ editLabel(edit) }}</div><div class="mt-1 text-[11px] text-ink-muted">{{ segmentForEdit(edit)?.text || "时间范围建议" }}</div></div><span class="shrink-0 text-[11px] text-ink-muted">{{ formatTimeShort(edit.start) }}</span></div>
          <div class="mt-2 flex gap-2"><button class="mc-button mc-button-primary min-h-8 flex-1 px-2 text-xs" @click="emit('confirm-edit', edit.id)">确认</button><button class="mc-button mc-button-secondary min-h-8 flex-1 px-2 text-xs" @click="emit('reject-edit', edit.id)">驳回</button></div>
        </article>
        <article v-for="correction in corrections" :key="correction.id" class="rounded-[var(--radius-control)] border border-hairline bg-canvas p-3">
          <div class="text-xs font-semibold text-ink">字幕纠错 · {{ Math.round(correction.confidence * 100) }}%</div>
          <p class="mt-2 text-xs leading-5 text-ink-muted"><span class="line-through">{{ correction.original_text }}</span><br><span class="text-primary">{{ correction.corrected_text }}</span></p>
          <div class="mt-2 flex gap-2"><button class="mc-button mc-button-primary min-h-8 flex-1 px-2 text-xs" @click="emit('accept-correction', correction.id)">接受</button><button class="mc-button mc-button-secondary min-h-8 flex-1 px-2 text-xs" @click="emit('reject-correction', correction.id)">保留原文</button></div>
        </article>
        <div class="rounded-[var(--radius-control)] bg-parchment p-3 text-xs text-ink-muted">已确认删除 {{ formatTimeShort(confirmedDeleteDuration) }}，导出摘要会实时更新。</div>
      </section>
    </main>

    <nav class="fixed inset-x-0 bottom-0 z-raised flex border-t border-hairline bg-canvas/95 p-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] backdrop-blur sm:absolute">
      <button v-for="item in sections" :key="item.key" class="mc-button min-h-9 flex-1 px-2 text-xs" :class="activeSection === item.key ? 'mc-button-primary' : 'mc-button-quiet'" @click="setSection(item.key)">{{ item.label }}</button>
    </nav>
  </div>
</template>

<style scoped>
.demo-range {
  height: 1rem;
}

.demo-range::-webkit-slider-runnable-track {
  height: 0.25rem;
  border-radius: 999px;
  background: var(--color-hairline);
}

.demo-range::-webkit-slider-thumb {
  margin-top: -0.25rem;
}
</style>
