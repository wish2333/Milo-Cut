<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue"
import type { AnalysisResult, EditDecision, Segment } from "@/types/project"
import { formatTime } from "@/utils/format"

const props = defineProps<{
  analysisResults: AnalysisResult[]
  edits: EditDecision[]
  segments: Segment[]
  pendingCorrectionCount?: number
}>()

const emit = defineEmits<{
  "confirm-edit": [editId: string]
  "reject-edit": [editId: string]
  "confirm-edit-batch": [editIds: string[]]
  "reject-edit-batch": [editIds: string[]]
  "delete-edit-batch": [editIds: string[]]
  "seek": [time: number]
  "review-corrections": []
}>()

// v3.0.4 M4-3 (P3-7): the manual group stays expanded by default -- unlike
// the analysis groups it only exists once the user has created ranges, so
// the first created range should be visible immediately.
const expandedGroups = ref<Set<string>>(new Set(["llm_smart", "partial_delete", "manual"]))

type ItemStatus = "pending" | "confirmed" | "rejected"
type ItemKind = "silence" | "llm_smart" | "partial_delete" | "manual"

interface SuggestionItem {
  id: string
  editId: string | undefined
  start: number
  end: number
  label: string
  type: ItemKind
  status: ItemStatus
  /** Manual ranges only: distinguishes 删除/保留 entries (SPEC M4-3). */
  action?: "delete" | "keep"
}

interface GroupedResult {
  type: ItemKind
  label: string
  items: SuggestionItem[]
  pendingCount: number
  confirmedCount: number
  rejectedCount: number
}

function statusOf(edit: EditDecision | undefined): ItemStatus {
  return edit?.status ?? "pending"
}

const groups = computed<GroupedResult[]>(() => {
  const result: GroupedResult[] = []
  const push = (type: ItemKind, label: string, items: SuggestionItem[]) => {
    if (items.length === 0) return
    result.push({
      type, label, items,
      pendingCount: items.filter(i => i.status === "pending").length,
      confirmedCount: items.filter(i => i.status === "confirmed").length,
      rejectedCount: items.filter(i => i.status === "rejected").length,
    })
  }

  const silenceItems: SuggestionItem[] = props.edits
    .filter(e => e.source === "silence_detection")
    .map(e => ({ id: e.id, editId: e.id, start: e.start, end: e.end, label: `静音 ${(e.end - e.start).toFixed(1)}s`, type: "silence" as const, status: statusOf(e) }))
  push("silence", "静音检测", silenceItems)

  const smartEdits = props.edits.filter(e => e.source === "llm_smart")
  const smartCategoryByAnalysisId = computed(() => {
    const m = new Map<string, string>()
    for (const r of props.analysisResults) {
      if (r.type === "llm_smart_delete" && r.category) {
        m.set(r.id, r.category)
      }
    }
    return m
  })
  const normalItems: SuggestionItem[] = []
  const partialItems: SuggestionItem[] = []
  for (const e of smartEdits) {
    const analysis = props.analysisResults.find(
      r => r.type === "llm_smart_delete" && e.target_id && r.segment_ids.includes(e.target_id)
    )
    const cat = e.analysis_id ? smartCategoryByAnalysisId.value.get(e.analysis_id) : ""
    const item = {
      id: e.id, editId: e.id, start: e.start, end: e.end,
      label: analysis?.detail || `智能删除 ${(e.end - e.start).toFixed(1)}s`,
      type: "llm_smart" as const, status: statusOf(e),
    }
    if (cat === "partial_delete") partialItems.push(item)
    else normalItems.push(item)
  }
  push("llm_smart", "智能删除", normalItems)
  push("partial_delete", "部分删除（需手动处理）", partialItems)

  // v3.0.4 M4-3 (P3-7): third source group -- manual ranges created via the
  // waveform bubble or the header timecode popover. Label prefix 删除/保留
  // is the per-entry action marker (SPEC M4-3 either/or ruling: no
  // sub-sections inside the group). Same empty-group guard as the others:
  // the whole group hides while no manual edit exists.
  const manualItems: SuggestionItem[] = props.edits
    .filter(e => e.source === "manual")
    .map(e => ({
      id: e.id,
      editId: e.id,
      start: e.start,
      end: e.end,
      label: `${e.action === "keep" ? "保留" : "删除"} ${(e.end - e.start).toFixed(1)}s`,
      type: "manual" as const,
      status: statusOf(e),
      action: e.action,
    }))
  push("manual", "手动范围", manualItems)

  return result
})

const SUGGESTION_SOURCES = new Set(["silence_detection", "llm_smart", "manual"])

// v3.0.4 M4-3 (P3-7): manual ranges join the header counters and BOTH
// actions count (keep entries are review work too); the two legacy sources
// keep their delete-only filter byte-for-byte (they never produce keep
// edits, so their counts are unchanged in every existing scenario).
function isCounted(e: EditDecision): boolean {
  return SUGGESTION_SOURCES.has(e.source) && (e.source === "manual" || e.action === "delete")
}

const totalPending = computed(() => props.edits.filter(e =>
  e.status === "pending" && isCounted(e)
).length)
const totalAll = computed(() => props.edits.filter(e => isCounted(e)).length)

function toggleGroup(type: string) {
  if (expandedGroups.value.has(type)) expandedGroups.value.delete(type)
  else expandedGroups.value.add(type)
}
function isExpanded(type: string): boolean { return expandedGroups.value.has(type) }
function handleSeek(item: SuggestionItem) { emit("seek", item.start) }
function handleAction(item: SuggestionItem, action: "confirm" | "reject") {
  if (!item.editId) return
  if (action === "confirm") emit("confirm-edit", item.editId)
  else emit("reject-edit", item.editId)
}

// v3.0.4 M4-3 (P3-7): manual-range confirm wording -- confirm feeds the
// trim computation, it is NOT an export action (keep entries especially:
// the confirmed keep range is subtracted from the auto-trim deletions,
// SPEC M4-4). Legacy groups keep no title (DOM unchanged).
function confirmTitle(item: SuggestionItem): string | undefined {
  if (item.type !== "manual") return undefined
  return item.action === "keep"
    ? "确认 = 参与裁剪计算（保留区间将从自动裁剪中扣除；非导出动作）"
    : "确认 = 参与裁剪计算（非导出动作）"
}

// -- Timecode popover (v3.0.4 M4-3 / SPEC M4-2 timecode entry) -----------
//
// The panel lives inside Timeline's subtree, so a new emit would need a
// Timeline relay (red line: untouched). The page instead hands its
// handleRangeDecision (the SAME handler the M4-2 bubble uses: snapshot
// ["edits"] -> add_range_decision -> project-updated patch) down via
// injection -- the WORKSPACE_ACTIONS_KEY pattern for page -> deep-child
// wiring. String key: the red line's file list leaves no shared symbol
// module to host an InjectionKey.
type AddRangeDecisionPayload = { start: number; end: number; action: "delete" | "keep" }
const addRangeDecision = inject<((payload: AddRangeDecisionPayload) => Promise<void>) | null>(
  "suggestion:add-range-decision",
  null,
)

const timecodeOpen = ref(false)
// v-model on type="number" inputs auto-casts to number (Vue behavior), so
// the refs hold string | number; empty fields arrive as "".
const timecodeStart = ref<string | number>("")
const timecodeEnd = ref<string | number>("")
// Default delete mirrors the bubble's default focus (SPEC M4-2 Q9).
const timecodeAction = ref<"delete" | "keep">("delete")
const timecodeError = ref("")

function closeTimecode() {
  timecodeOpen.value = false
  timecodeError.value = ""
}

function submitTimecode() {
  const startText = String(timecodeStart.value ?? "").trim()
  const endText = String(timecodeEnd.value ?? "").trim()
  const start = Number(startText)
  const end = Number(endText)
  // Empty / non-numeric input and end<=start are rejected in place -- the
  // bridge is never called for invalid input.
  if (startText === "" || endText === "" || !Number.isFinite(start) || !Number.isFinite(end)) {
    timecodeError.value = "请输入有效的起止时间（秒，支持小数）"
    return
  }
  if (end <= start) {
    timecodeError.value = "结束时间必须大于开始时间"
    return
  }
  timecodeError.value = ""
  if (!addRangeDecision) return // unwired host (never in production)
  void addRangeDecision({ start, end, action: timecodeAction.value })
  closeTimecode()
}

// -- Context menu --------------------------------------------------------

interface ContextMenuState {
  x: number
  y: number
  scope: "item" | "group"
  item?: SuggestionItem
  group?: GroupedResult
}

const contextMenu = ref<ContextMenuState | null>(null)

function openItemMenu(e: MouseEvent, item: SuggestionItem) {
  e.preventDefault()
  contextMenu.value = { x: e.clientX, y: e.clientY, scope: "item", item }
}

function openGroupMenu(e: MouseEvent, group: GroupedResult) {
  e.preventDefault()
  contextMenu.value = { x: e.clientX, y: e.clientY, scope: "group", group }
}

function closeContextMenu() {
  contextMenu.value = null
}

function groupEditIds(group: GroupedResult): string[] {
  return group.items.map(i => i.editId).filter((id): id is string => !!id)
}

function runGroupAction(group: GroupedResult, action: "confirm" | "reject" | "delete") {
  const ids = groupEditIds(group)
  if (ids.length === 0) { closeContextMenu(); return }
  if (action === "confirm") emit("confirm-edit-batch", ids)
  else if (action === "reject") emit("reject-edit-batch", ids)
  else if (action === "delete") {
    // Permanent deletion is irreversible; confirm with explicit wording
    if (!confirm(`确认永久删除「${group.label}」中的 ${ids.length} 条建议（含已确认/已忽略）？此操作不可撤销。`)) {
      closeContextMenu()
      return
    }
    emit("delete-edit-batch", ids)
  }
  closeContextMenu()
}

function runItemActionFromMenu(action: "confirm" | "reject") {
  const item = contextMenu.value?.item
  if (item) handleAction(item, action)
  closeContextMenu()
}

// v3.0.4 smoke-fix 2: per-item permanent delete for manual ranges -- the
// item context menu only offered 确认/忽略, so a single unwanted range had
// no delete affordance (smoke finding). Reuses the existing batch channel
// with a single id; downstream (delete_edit_decisions_batch) is unchanged.
function runItemDeleteFromMenu() {
  const item = contextMenu.value?.item
  if (!item?.editId) { closeContextMenu(); return }
  if (!confirm(`确认永久删除该${item.label}范围？此操作不可撤销。`)) {
    closeContextMenu()
    return
  }
  emit("delete-edit-batch", [item.editId])
  closeContextMenu()
}

function onWindowClick() {
  if (contextMenu.value) closeContextMenu()
  // The toggle button and the popover itself stop propagation, so any
  // click that reaches here is outside -> close (v3.0.4 M4-3).
  if (timecodeOpen.value) closeTimecode()
}

function onWindowKeydown(e: KeyboardEvent) {
  if (e.key !== "Escape") return
  if (contextMenu.value) closeContextMenu()
  else if (timecodeOpen.value) closeTimecode()
}

onMounted(() => {
  window.addEventListener("click", onWindowClick)
  window.addEventListener("keydown", onWindowKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener("click", onWindowClick)
  window.removeEventListener("keydown", onWindowKeydown)
})
</script>
<template>
  <div class="overflow-hidden border border-hairline bg-parchment">
    <!-- v3.0.4 M4-3 (P3-7): the header bar is ALWAYS rendered -- the
         timecode entry lives here (SPEC M4-2 R3 ruling) so an empty
         project can create its first manual range (the manual group is
         hidden by the empty-group guard while unused). -->
    <div class="relative border-b border-hairline px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <span class="min-w-0">
          <span class="text-sm font-semibold text-ink">
            共 {{ totalAll }} 处建议
            <template v-if="totalPending > 0">
              | {{ totalPending }} 处待处理
            </template>
          </span>
          <span class="ml-2 text-xs text-ink-muted">右键单项/组可批量操作</span>
        </span>
        <button
          type="button"
          data-test="timecode-toggle"
          class="mc-button mc-button-secondary min-h-7 shrink-0 px-2 py-0.5 text-xs"
          @click.stop="timecodeOpen = !timecodeOpen"
        >
          + 时间码
        </button>
      </div>

      <!-- Timecode popover: precise manual ranges for oral-delivery
           editing. Same add_range_decision path as the waveform bubble. -->
      <div
        v-if="timecodeOpen"
        data-test="timecode-popover"
        class="absolute top-full right-0 z-dropdown mt-1 w-64 rounded-md border border-gray-200 bg-white p-3 text-left shadow-lg"
        @click.stop
      >
        <div class="mb-2 text-xs font-semibold text-ink">添加手动范围（秒，支持小数）</div>
        <div class="flex items-center gap-1.5">
          <label class="shrink-0 text-xs text-gray-500" for="suggestion-timecode-start">起</label>
          <input
            id="suggestion-timecode-start"
            v-model="timecodeStart"
            data-test="timecode-start"
            type="number"
            step="0.1"
            min="0"
            placeholder="如 12.5"
            class="w-full rounded border border-gray-300 px-2 py-1 text-sm outline-none focus:border-blue-400"
          />
          <label class="shrink-0 text-xs text-gray-500" for="suggestion-timecode-end">止</label>
          <input
            id="suggestion-timecode-end"
            v-model="timecodeEnd"
            data-test="timecode-end"
            type="number"
            step="0.1"
            min="0"
            placeholder="如 15.0"
            class="w-full rounded border border-gray-300 px-2 py-1 text-sm outline-none focus:border-blue-400"
          />
        </div>
        <div class="mt-2 flex items-center gap-1.5">
          <span class="shrink-0 text-xs text-gray-500">类型</span>
          <button
            type="button"
            data-test="timecode-action-delete"
            class="mc-button min-h-7 px-2 py-0.5 text-xs"
            :class="timecodeAction === 'delete' ? 'mc-button-primary' : 'mc-button-secondary'"
            @click="timecodeAction = 'delete'"
          >
            删除
          </button>
          <button
            type="button"
            data-test="timecode-action-keep"
            class="mc-button min-h-7 px-2 py-0.5 text-xs"
            :class="timecodeAction === 'keep' ? 'mc-button-primary' : 'mc-button-secondary'"
            @click="timecodeAction = 'keep'"
          >
            保留
          </button>
        </div>
        <div v-if="timecodeError" data-test="timecode-error" class="mt-2 text-xs text-red-600">
          {{ timecodeError }}
        </div>
        <div class="mt-2 flex justify-end gap-2">
          <button
            type="button"
            class="mc-button mc-button-secondary min-h-7 px-2 py-0.5 text-xs"
            @click="closeTimecode"
          >
            取消
          </button>
          <button
            type="button"
            data-test="timecode-submit"
            class="mc-button mc-button-primary min-h-7 px-2 py-0.5 text-xs"
            @click="submitTimecode"
          >
            添加
          </button>
        </div>
      </div>
    </div>

    <button
      v-if="(pendingCorrectionCount ?? 0) > 0"
      class="flex w-full items-center justify-between border-b border-hairline bg-primary-soft px-3 py-2 text-left transition-colors hover:bg-white"
      @click="emit('review-corrections')"
    >
      <span class="text-sm font-semibold text-primary">
        P1 字幕修正待审 ({{ pendingCorrectionCount }} 条)
      </span>
      <span class="text-xs text-primary">查看详情 →</span>
    </button>

    <div v-if="groups.length === 0" class="px-3 py-6 text-center text-sm text-ink-muted">
      暂无分析结果
    </div>

    <div v-for="group in groups" :key="group.type" class="border-b border-hairline last:border-b-0">
      <button
          class="flex w-full items-center justify-between px-3 py-2 transition-colors hover:bg-canvas"
        @click="toggleGroup(group.type)"
        @contextmenu="openGroupMenu($event, group)"
      >
        <span class="text-sm font-semibold">
          {{ isExpanded(group.type) ? "v" : ">" }} {{ group.label }}
        </span>
        <span class="flex items-center gap-1.5 text-xs">
          <span v-if="group.pendingCount > 0" class="text-gray-500">待{{ group.pendingCount }}</span>
          <span v-if="group.confirmedCount > 0" class="text-green-700">已确认{{ group.confirmedCount }}</span>
          <span v-if="group.rejectedCount > 0" class="text-gray-400">已忽略{{ group.rejectedCount }}</span>
          <span class="text-gray-400">共{{ group.items.length }}</span>
          <!-- v3.0.4 smoke-fix 2: visible one-click clear for manual ranges
               (the group right-click menu existed but was undiscoverable).
               Left-click = same guarded batch delete; stop propagation so
               the header toggle does not fold the group. -->
          <button
            v-if="group.type === 'manual'"
            class="rounded bg-red-50 px-1.5 py-0.5 text-[11px] leading-none text-red-600 transition-colors hover:bg-red-100"
            data-test="manual-group-clear"
            title="一键清除本组全部手动范围（含已确认/已忽略，永久删除）"
            @click.stop="runGroupAction(group, 'delete')"
          >
            清除
          </button>
        </span>
      </button>

      <div v-if="isExpanded(group.type)" class="divide-y divide-gray-50">
        <div
          v-for="item in group.items"
          :key="item.id"
          class="flex items-start gap-2 px-3 py-1.5 cursor-pointer transition-colors"
          :class="{
            'hover:bg-canvas': item.status === 'pending',
            'bg-status-rejected hover:bg-green-50': item.status === 'confirmed',
            'opacity-50 hover:opacity-70': item.status === 'rejected',
          }"
          @click="handleSeek(item)"
          @contextmenu="openItemMenu($event, item)"
        >
          <span class="text-xs text-gray-400 w-12 shrink-0 font-mono pt-0.5">
            {{ formatTime(item.start) }}
          </span>

          <!-- v3.0.4 M4-3: manual entries carry an explicit pending badge so
               all three states are visible (legacy groups: DOM unchanged,
               pending stays badge-less as before). -->
          <span
            v-if="item.type === 'manual' && item.status === 'pending'"
            class="shrink-0 pt-0.5 font-bold text-primary"
            title="待处理"
          >[·]</span>
          <span
            v-if="item.status === 'confirmed'"
            class="shrink-0 pt-0.5 font-bold text-green-700"
            title="已确认"
          >[Y]</span>
          <span
            v-else-if="item.status === 'rejected'"
            class="shrink-0 text-gray-400 pt-0.5 font-bold"
            title="已忽略"
          >[N]</span>

          <span
            class="flex-1 text-sm leading-snug break-words"
            :class="{ 'line-through text-gray-500': item.status === 'rejected' }"
          >
            {{ item.label }}
          </span>

          <span v-if="item.editId" class="flex items-center gap-1 shrink-0 pt-0.5">
            <button
              v-if="item.status !== 'confirmed'"
              class="mc-button mc-button-primary min-h-7 px-2 py-0.5 text-xs"
              :title="confirmTitle(item)"
              @click.stop="handleAction(item, 'confirm')"
            >
              确认
            </button>
            <button
              v-if="item.status !== 'rejected'"
              class="mc-button mc-button-secondary min-h-7 px-2 py-0.5 text-xs"
              @click.stop="handleAction(item, 'reject')"
            >
              忽略
            </button>
          </span>
        </div>
      </div>
    </div>

    <!-- Context menu (Teleport to body so it is never clipped) -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-dropdown min-w-[160px] py-1 bg-white border border-gray-200 rounded shadow-xl text-sm"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <template v-if="contextMenu.scope === 'item'">
          <button
            v-if="contextMenu.item?.status !== 'confirmed'"
            class="block w-full text-left px-3 py-1.5 hover:bg-blue-50 text-gray-700"
            @click="runItemActionFromMenu('confirm')"
          >
            确认此项
          </button>
          <button
            v-if="contextMenu.item?.status !== 'rejected'"
            class="block w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-700"
            @click="runItemActionFromMenu('reject')"
          >
            忽略此项
          </button>
          <!-- v3.0.4 smoke-fix 2: manual ranges get a permanent per-item
               delete (legacy groups keep their group-level delete only). -->
          <button
            v-if="contextMenu.item?.type === 'manual'"
            class="block w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600"
            @click="runItemDeleteFromMenu"
          >
            删除此项（永久，含已确认）
          </button>
        </template>
        <template v-else-if="contextMenu.scope === 'group' && contextMenu.group">
          <button
            class="block w-full text-left px-3 py-1.5 hover:bg-blue-50 text-gray-700"
            @click="runGroupAction(contextMenu.group, 'confirm')"
          >
            全部确认本组 ({{ contextMenu.group.items.length }})
          </button>
          <button
            class="block w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-700"
            @click="runGroupAction(contextMenu.group, 'reject')"
          >
            全部忽略本组 ({{ contextMenu.group.items.length }})
          </button>
          <button
            class="block w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600"
            @click="runGroupAction(contextMenu.group, 'delete')"
          >
            删除本组建议（{{ contextMenu.group.items.length }} 条，含已确认）
          </button>
        </template>
      </div>
    </Teleport>
  </div>
</template>
