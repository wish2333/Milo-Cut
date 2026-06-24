<template>
  <div class="flex items-center gap-2">
    <details class="dropdown dropdown-end" :open="dropdownOpen" @toggle="onToggle">
      <summary class="flex items-center gap-2 rounded px-2 py-1 text-xs text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer list-none">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2H7a2 2 0 00-2 2v2m4-4h6" />
        </svg>
        <span class="max-w-[120px] truncate">{{ activeLabel }}</span>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </summary>
      <ul class="dropdown-content z-50 menu p-2 shadow-lg bg-base-100 rounded-box w-64 border border-base-300">
        <li v-for="tl in timelines" :key="tl.id">
          <a
            class="flex items-center justify-between"
            :class="{ 'active': tl.id === activeTimelineId }"
            @click="onSwitch(tl.id)"
            @contextmenu.prevent.stop="onContextMenu($event, tl.id)"
          >
            <div class="flex flex-col min-w-0">
              <!-- v2.1.1 M4-5: inline rename -->
              <input
                v-if="renamingId === tl.id"
                :value="renameVal"
                class="text-sm font-medium bg-transparent border-b border-blue-400 outline-none w-full"
                :ref="(el) => { if (el) (el as HTMLInputElement).focus() }"
                @click.stop
                @input="$emit('rename-input', tl.id, ($event.target as HTMLInputElement).value)"
                @keydown.enter.stop.prevent="$emit('rename-confirm', tl.id)"
                @keydown.escape.stop.prevent="$emit('rename-cancel')"
                @blur="$emit('rename-confirm', tl.id)"
              />
              <span v-else class="truncate text-sm font-medium">{{ tl.label }}</span>
              <span v-if="tl.source !== 'default'" class="text-xs opacity-60">{{ tl.source }}</span>
            </div>
            <div v-if="tl.id === activeTimelineId" class="text-success">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </div>
          </a>
        </li>
        <div class="divider my-1"></div>
        <li>
          <a class="text-sm" @click="$emit('create')">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            新建 Timeline
          </a>
        </li>
        <li v-if="canDelete">
          <a class="text-sm text-error" @click="$emit('delete', activeTimelineId)">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3" />
            </svg>
            删除当前
          </a>
        </li>
      </ul>
    </details>

    <!-- v2.1.1 M4-5: timeline right-click context menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-[9999] bg-white rounded-md shadow-lg border border-gray-200 py-1 min-w-[140px]"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop="contextMenu = null"
      >
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          @click="onContextRename"
        >
          重命名
        </button>
        <div class="border-t border-gray-100 my-1" />
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
          :disabled="!canDelete"
          @click="onContextDelete"
        >
          删除
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import type { Timeline } from "@/types/project"
import { openContextMenu } from "@/utils/contextMenuManager"

const props = defineProps<{
  timelines: Timeline[]
  activeTimelineId: string
  /** v2.1.1 M4-5: id of the timeline currently being renamed */
  renamingId?: string | null
  /** v2.1.1 M4-5: current rename input value */
  renameVal?: string
}>()

const emit = defineEmits<{
  switch: [timelineId: string]
  create: []
  delete: [timelineId: string]
  // v2.1.1 M4-5: rename
  "rename-start": [timelineId: string]
  "rename-input": [timelineId: string, value: string]
  "rename-confirm": [timelineId: string]
  "rename-cancel": []
}>()

const contextMenu = ref<{ x: number; y: number; id: string } | null>(null)

// v2.1.1 A-4: explicit dropdown open state. <details> element gives us
// programmatic control so the dropdown no longer auto-collapses when focus
// leaves the trigger (the root cause of "rename hides the switcher").
const dropdownOpen = ref(false)

function onToggle(e: ToggleEvent) {
  dropdownOpen.value = (e.target as HTMLDetailsElement).open
}

const activeLabel = computed(() => {
  const tl = props.timelines.find(t => t.id === props.activeTimelineId)
  return tl?.label ?? ""
})

const canDelete = computed(() => props.timelines.length > 1)

function onSwitch(id: string) {
  // Don't switch if the clicked row is in rename-edit mode
  if (props.renamingId === id) return
  emit("switch", id)
}

function onContextMenu(e: MouseEvent, id: string) {
  contextMenu.value = { x: e.clientX, y: e.clientY, id }
  openContextMenu(() => { contextMenu.value = null })
}

function onContextRename() {
  const id = contextMenu.value?.id
  contextMenu.value = null
  if (id) {
    // 先切换到目标 Timeline，再进入重命名
    if (id !== props.activeTimelineId) emit("switch", id)
    // Force the dropdown to stay open so the inline rename input is visible.
    dropdownOpen.value = true
    emit("rename-start", id)
  }
}

function onContextDelete() {
  const id = contextMenu.value?.id
  contextMenu.value = null
  if (id && canDelete.value) emit("delete", id)
}

// Autofocus the inline rename input when it mounts
// (handled inline via @vue:mounted now)
</script>
