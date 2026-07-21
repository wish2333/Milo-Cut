import { afterEach, describe, expect, it, vi } from "vitest"
import { callDemo } from "./demoBridge"
import { demoStore } from "./demoStore"
import { EVENT_TASK_COMPLETED, EVENT_WORKFLOW_CONFLICTS_DETECTED } from "@/utils/events"

describe("demoBridge", () => {
  afterEach(() => {
    vi.useRealTimers()
    demoStore.reset()
  })

  it("returns the standard API envelope and protects unsupported methods", async () => {
    const project = await callDemo("get_project")
    expect(project.success).toBe(true)
    expect(project.data).toBeTruthy()
    const unsupported = await callDemo("probe_media", "demo.mp4")
    expect(unsupported).toEqual({ success: false, error: "该功能仅在桌面版可用" })
  })

  it("returns complete settings for the Settings modal", async () => {
    const response = await callDemo("get_settings")
    expect(response.success).toBe(true)
    expect(typeof (response.data as { llm_base_url: unknown }).llm_base_url).toBe("string")
    expect((response.data as { llm_provider_configs: unknown }).llm_provider_configs).toBeTruthy()
  })

  it("runs a deterministic task and emits completion with the updated project", async () => {
    vi.useFakeTimers()
    const completed = vi.fn()
    window.addEventListener(`pywebvue:${EVENT_TASK_COMPLETED}`, completed)
    const task = await callDemo<{ id: string }>("create_task", "export_video")
    expect(task.success).toBe(true)
    await callDemo("start_task", task.data!.id)
    vi.advanceTimersByTime(1000)
    expect(completed).toHaveBeenCalled()
    expect(demoStore.state.exportHistory).toHaveLength(1)
    window.removeEventListener(`pywebvue:${EVENT_TASK_COMPLETED}`, completed)
  })

  it("exposes the deterministic workflow conflict and resolves its edit", async () => {
    vi.useFakeTimers()
    const conflicts = vi.fn()
    window.addEventListener(`pywebvue:${EVENT_WORKFLOW_CONFLICTS_DETECTED}`, conflicts)
    await callDemo("start_workflow", "demo-workflow")
    vi.advanceTimersByTime(3200)
    expect(conflicts).toHaveBeenCalled()
    const target = demoStore.state.project.timelines[0].edits.find((edit) => edit.source === "llm_smart")
    const segment = target?.target_id
    expect(segment).toBeTruthy()
    await callDemo("resolve_workflow_conflict", segment, "keep_last")
    expect(demoStore.state.project.timelines[0].edits.find((edit) => edit.id === target?.id)?.status).toBe("rejected")
    window.removeEventListener(`pywebvue:${EVENT_WORKFLOW_CONFLICTS_DETECTED}`, conflicts)
  })
})
