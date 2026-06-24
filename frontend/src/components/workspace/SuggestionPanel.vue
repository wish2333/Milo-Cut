<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
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
  "reset-edit": [editId: string]
  "confirm-edit-batch": [editIds: string[]]
  "reject-edit-batch": [editIds: string[]]
  "reset-edit-batch": [editIds: string[]]
  "delete-edit-batch": [editIds: string[]]
  "confirm-all": []
  "reject-all": []
  "seek": [time: number]
  "review-corrections": []
}>()

const expandedGroups = ref<Set<string>>(new Set(["llm_smart", "partial_delete"]))

type ItemStatus = "pending" | "confirmed" | "rejected"
type ItemKind = "silence" | "llm_smart" | "partial_delete"

interface SuggestionItem {
  id: string
  editId: string | undefined
  start: number
  end: number
  label: string
  type: ItemKind
  status: ItemStatus
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
  push("partial_delete" as any, "部分删除（需手动处理）", partialItems)

  return result
})

const totalPending = computed(() => props.edits.filter(e => e.status === "pending" && e.action === "delete").length)
const totalAll = computed(() => props.edits.filter(e => e.action === "delete").length)

function toggleGroup(type: string) {
  if (expandedGroups.value.has(type)) expandedGroups.value.delete(type)
  else expandedGroups.value.add(type)
}
function isExpanded(type: string): boolean { return expandedGroups.value.has(type) }
function handleSeek(item: SuggestionItem) { emit("seek", item.start) }
function handleAction(item: SuggestionItem, action: "confirm" | "reject" | "reset") {
  if (!item.editId) return
  if (action === "confirm") emit("confirm-edit", item.editId)
  else if (action === "reject") emit("reject-edit", item.editId)
  else emit("reset-edit", item.editId)
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

function runGroupAction(group: GroupedResult, action: "confirm" | "reject" | "reset" | "delete") {
  const ids = groupEditIds(group)
  if (ids.length === 0) { closeContextMenu(); return }
  if (action === "confirm") emit("confirm-edit-batch", ids)
  else if (action === "reject") emit("reject-edit-batch", ids)
  else if (action === "reset") emit("reset-edit-batch", ids)
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

function runItemActionFromMenu(action: "confirm" | "reject" | "reset") {
  const item = contextMenu.value?.item
  if (item) handleAction(item, action)
  closeContextMenu()
}

function onWindowClick() {
  if (contextMenu.value) closeContextMenu()
}

function onWindowKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && contextMenu.value) closeContextMenu()
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
  <div class="border border-gray-200 rounded-lg overflow-hidden">
    <div class="px-3 py-2 bg-gray-50 border-b border-gray-200">
      <span class="text-sm font-medium text-gray-700">
        共 {{ totalAll }} 处建议
        <template v-if="totalPending > 0">
          | {{ totalPending }} 处待处理
        </template>
      </span>
      <span class="ml-2 text-xs text-gray-400">右键单项/组可批量操作</span>
    </div>

    <button
      v-if="(pendingCorrectionCount ?? 0) > 0"
      class="flex w-full items-center justify-between border-b border-blue-100 bg-blue-50 px-3 py-2 text-left transition-colors hover:bg-blue-100"
      @click="emit('review-corrections')"
    >
      <span class="text-sm font-medium text-blue-700">
        P1 字幕修正待审 ({{ pendingCorrectionCount }} 条)
      </span>
      <span class="text-xs text-blue-500">查看详情 →</span>
    </button>

    <div v-if="groups.length === 0" class="px-3 py-4 text-center text-sm text-gray-400">
      暂无分析结果
    </div>

    <div v-for="group in groups" :key="group.type" class="border-b border-gray-100 last:border-b-0">
      <button
        class="flex items-center justify-between w-full px-3 py-2 hover:bg-gray-50 transition-colors"
        @click="toggleGroup(group.type)"
        @contextmenu="openGroupMenu($event, group)"
      >
        <span class="text-sm font-medium">
          {{ isExpanded(group.type) ? "v" : ">" }} {{ group.label }}
        </span>
        <span class="flex items-center gap-1.5 text-xs">
          <span v-if="group.pendingCount > 0" class="text-gray-500">待{{ group.pendingCount }}</span>
          <span v-if="group.confirmedCount > 0" class="text-green-600">已确认{{ group.confirmedCount }}</span>
          <span v-if="group.rejectedCount > 0" class="text-gray-400">已忽略{{ group.rejectedCount }}</span>
          <span class="text-gray-400">共{{ group.items.length }}</span>
        </span>
      </button>

      <div v-if="isExpanded(group.type)" class="divide-y divide-gray-50">
        <div
          v-for="item in group.items"
          :key="item.id"
          class="flex items-start gap-2 px-3 py-1.5 cursor-pointer transition-colors"
          :class="{
            'hover:bg-gray-50': item.status === 'pending',
            'bg-green-50/60 hover:bg-green-50': item.status === 'confirmed',
            'opacity-50 hover:opacity-70': item.status === 'rejected',
          }"
          @click="handleSeek(item)"
          @contextmenu="openItemMenu($event, item)"
        >
          <span class="text-xs text-gray-400 w-12 shrink-0 font-mono pt-0.5">
            {{ formatTime(item.start) }}
          </span>

          <span
            v-if="item.status === 'confirmed'"
            class="shrink-0 text-green-600 pt-0.5 font-bold"
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
              class="text-xs px-2 py-0.5 rounded bg-blue-500 text-white hover:bg-blue-600"
              @click.stop="handleAction(item, 'confirm')"
            >
              确认
            </button>
            <button
              v-if="item.status !== 'rejected'"
              class="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600 hover:bg-gray-300"
              @click.stop="handleAction(item, 'reject')"
            >
              忽略
            </button>
            <button
              v-if="item.status !== 'pending'"
              class="text-xs px-2 py-0.5 rounded border border-gray-300 text-gray-500 hover:bg-gray-100"
              title="撤销状态恢复待处理"
              @click.stop="handleAction(item, 'reset')"
            >
              撤销
            </button>
          </span>
        </div>
      </div>
    </div>

    <div v-if="totalPending > 0" class="flex gap-2 px-3 py-2 bg-gray-50">
      <button
        class="flex-1 text-sm px-3 py-1.5 rounded-full bg-blue-500 text-white hover:bg-blue-600 transition-colors"
        @click="emit('confirm-all')"
      >
        全部确认删除
      </button>
      <button
        class="flex-1 text-sm px-3 py-1.5 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
        @click="emit('reject-all')"
      >
        忽略所有建议
      </button>
    </div>

    <!-- Context menu (Teleport to body so it is never clipped) -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-50 min-w-[160px] py-1 bg-white border border-gray-200 rounded shadow-xl text-sm"
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
          <button
            v-if="contextMenu.item?.status !== 'pending'"
            class="block w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-700"
            @click="runItemActionFromMenu('reset')"
          >
            撤销此项
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
            class="block w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-700"
            @click="runGroupAction(contextMenu.group, 'reset')"
          >
            全部撤销本组
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
