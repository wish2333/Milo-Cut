<template>
  <div class="flex items-center gap-2">
    <div class="dropdown dropdown-end">
      <div tabindex="0" role="button" class="flex items-center gap-2 rounded px-2 py-1 text-xs text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2H7a2 2 0 00-2 2v2m4-4h6" />
        </svg>
        <span class="max-w-[120px] truncate">{{ activeLabel }}</span>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
      <ul tabindex="0" class="dropdown-content z-50 menu p-2 shadow-lg bg-base-100 rounded-box w-64 border border-base-300">
        <li v-for="tl in timelines" :key="tl.id">
          <a
            class="flex items-center justify-between"
            :class="{ 'active': tl.id === activeTimelineId }"
            @click="$emit('switch', tl.id)"
          >
            <div class="flex flex-col min-w-0">
              <span class="truncate text-sm font-medium">{{ tl.label }}</span>
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import type { Timeline } from "@/types/project"

const props = defineProps<{
  timelines: Timeline[]
  activeTimelineId: string
}>()

defineEmits<{
  switch: [timelineId: string]
  create: []
  delete: [timelineId: string]
}>()

const activeLabel = computed(() => {
  const tl = props.timelines.find(t => t.id === props.activeTimelineId)
  return tl?.label ?? ""
})

const canDelete = computed(() => props.timelines.length > 1)
</script>
