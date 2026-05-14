<script setup lang="ts">
import { ref } from "vue"
import WelcomePage from "@/pages/WelcomePage.vue"
import WorkspacePage from "@/pages/WorkspacePage.vue"
import { waitForPyWebView } from "./bridge"
import type { Project } from "@/types/project"

const ready = ref(false)
const bridgeError = ref("")
const project = ref<Project | null>(null)

waitForPyWebView(10_000)
  .then(() => {
    ready.value = true
  })
  .catch((err: unknown) => {
    bridgeError.value = err instanceof Error ? err.message : "Bridge init failed"
  })

function onProjectCreated(data: Project) {
  project.value = data
}
</script>

<template>
  <div v-if="bridgeError" class="flex min-h-screen items-center justify-center bg-canvas">
    <div class="text-center">
      <p class="text-lg font-semibold text-status-warning">Bridge Error</p>
      <p class="mt-2 text-sm text-ink-muted">{{ bridgeError }}</p>
    </div>
  </div>

  <div v-else-if="!ready" class="flex min-h-screen items-center justify-center bg-canvas">
    <div class="text-center">
      <p class="text-lg font-semibold text-ink">Milo-Cut</p>
      <p class="mt-2 text-sm text-ink-muted">正在连接后端...</p>
    </div>
  </div>

  <WelcomePage v-else-if="!project" @project-created="onProjectCreated" />

  <WorkspacePage v-else :project="project" />
</template>
