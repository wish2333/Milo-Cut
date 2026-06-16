<script setup lang="ts">
/**
 * Conflict Resolution View (v2.1.0 Phase 3, D-16, D-17, D-66).
 *
 * Full-screen overlay shown when workflow completes with EditDecision conflicts.
 * Users can resolve each conflict (keep delete / keep highlight / keep all),
 * or skip conflict resolution entirely (D-17: optional flow).
 */
import { computed, ref } from "vue"
import { useWorkflow } from "@/composables/useWorkflow"
import type { WorkflowConflict } from "@/composables/useWorkflow"

const wf = useWorkflow()

const currentIndex = ref(0)

const conflicts = computed(() => wf.conflicts.value)
const totalConflicts = computed(() => conflicts.value.length)
const currentConflict = computed<WorkflowConflict | null>(() => {
  if (currentIndex.value < conflicts.value.length) {
    return conflicts.value[currentIndex.value]
  }
  return null
})

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

function stepLabel(stepType: string): string {
  const labels: Record<string, string> = {
    full_analysis: "规则分析",
    llm_smart_delete: "P0 智能删除",
    llm_subtitle_correction: "P1 字幕修正",
    llm_highlight: "P2 精华提取",
  }
  return labels[stepType] || stepType
}

function actionLabel(action: string): string {
  if (action === "delete") return "删除"
  if (action === "keep") return "保留"
  return action
}

async function resolve(resolution: "keep_first" | "keep_last" | "keep_all") {
  if (!currentConflict.value) return
  await wf.resolveConflict(currentConflict.value.segment_id, resolution)
  // Move to next conflict
  if (currentIndex.value < totalConflicts.value - 1) {
    currentIndex.value++
  }
}

function skipAll() {
  // D-17: skip conflict resolution, keep all decisions
  wf.showConflictView.value = false
}

async function finishAndApply() {
  wf.showConflictView.value = false
  await wf.applyWorkflow()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="wf.showConflictView.value"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    >
      <div class="flex h-[80vh] w-[700px] max-w-[90vw] flex-col rounded-xl bg-white shadow-2xl">
        <!-- Header -->
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold text-gray-800">
            冲突解决
            <span class="ml-2 text-sm font-normal text-gray-400">
              {{ totalConflicts }} 个冲突
            </span>
          </h2>
          <button
            class="text-xs text-gray-400 hover:text-gray-600"
            @click="skipAll"
          >
            跳过冲突解决
          </button>
        </div>

        <!-- Body -->
        <div class="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
          <p v-if="totalConflicts === 0" class="text-center text-sm text-gray-500 py-8">
            没有需要解决的冲突
          </p>

          <template v-else-if="currentConflict">
            <!-- Conflict counter -->
            <div class="text-xs text-gray-500">
              冲突 {{ currentIndex + 1 }}/{{ totalConflicts }}
            </div>

            <!-- Segment info -->
            <div class="rounded-lg border border-gray-200 p-4">
              <div class="mb-2 flex items-center gap-2 text-xs text-gray-400">
                <span>{{ formatTime(currentConflict.segment_start) }} - {{ formatTime(currentConflict.segment_end) }}</span>
              </div>
              <p class="text-sm text-gray-700">
                {{ currentConflict.segment_text || "(无文本)" }}
              </p>
            </div>

            <!-- Competing decisions -->
            <div class="flex flex-col gap-2">
              <div
                v-for="(decision, i) in currentConflict.decisions"
                :key="decision.edit_id"
                class="flex items-center justify-between rounded-lg border px-4 py-3"
                :class="{
                  'border-red-200 bg-red-50': decision.action === 'delete',
                  'border-green-200 bg-green-50': decision.action === 'keep',
                }"
              >
                <div class="flex flex-col gap-1">
                  <span class="text-sm font-medium text-gray-700">
                    {{ stepLabel(decision.step_type) }} 建议:
                    <span
                      :class="{
                        'text-red-600': decision.action === 'delete',
                        'text-green-600': decision.action === 'keep',
                      }"
                    >{{ actionLabel(decision.action) }}</span>
                  </span>
                  <span v-if="decision.reason" class="text-xs text-gray-400">
                    {{ decision.reason }}
                  </span>
                </div>
                <span class="text-xs text-gray-300">#{{ i + 1 }}</span>
              </div>
            </div>
          </template>

          <!-- All resolved -->
          <div v-else class="flex flex-col items-center gap-3 py-8">
            <p class="text-sm text-gray-600">所有冲突已解决</p>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between border-t px-6 py-4">
          <!-- Skip / All-resolved -->
          <button
            class="rounded-md px-4 py-2 text-xs font-medium text-gray-500 hover:bg-gray-100"
            @click="skipAll"
          >
            跳过冲突解决
          </button>

          <!-- Resolution buttons -->
          <div v-if="currentConflict" class="flex gap-2">
            <button
              class="rounded-md border border-red-300 px-4 py-2 text-xs font-medium text-red-600 hover:bg-red-50"
              @click="resolve('keep_first')"
            >
              {{ currentConflict.decisions[0]?.action === 'delete' ? '保留删除' : '保留此建议' }}
            </button>
            <button
              class="rounded-md border border-green-300 px-4 py-2 text-xs font-medium text-green-600 hover:bg-green-50"
              @click="resolve('keep_last')"
            >
              {{ currentConflict.decisions[currentConflict.decisions.length - 1]?.action === 'keep' ? '保留精华' : '保留此建议' }}
            </button>
            <button
              class="rounded-md border border-gray-300 px-4 py-2 text-xs font-medium text-gray-600 hover:bg-gray-50"
              @click="resolve('keep_all')"
            >
              两者都保留
            </button>
          </div>

          <!-- Finish button -->
          <button
            v-else
            class="rounded-md bg-blue-500 px-6 py-2 text-xs font-medium text-white hover:bg-blue-600"
            @click="finishAndApply"
          >
            全部解决后继续
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
