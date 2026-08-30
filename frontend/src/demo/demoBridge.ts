import type { ApiResponse } from "@/bridge"
import type { EditDecision } from "@/types/project"
import type { AppSettings } from "@/types/edit"
import { createDemoTask, startDemoLlmTask, startDemoTask, startDemoWorkflow, cancelDemoTask, emitDemoEvent, resetDemoTasks } from "./demoTaskRunner"
import { demoStore } from "./demoStore"
import { EVENT_DEMO_PROJECT_UPDATED, EVENT_DEMO_RESET } from "@/utils/events"

const unsupported = <T = unknown>(): ApiResponse<T> => ({ success: false, error: "该功能仅在桌面版可用" })
const ok = <T>(data: T): ApiResponse<T> => ({ success: true, data })

function getDemoSettings(): AppSettings {
  return {
    ffmpeg_path: "",
    ffprobe_path: "",
    theme: "light",
    language: "zh-CN",
    silence_threshold_db: -30,
    silence_min_duration: 0.5,
    silence_margin: 0,
    silence_subtitle_padding: 0,
    trim_subtitles_on_silence_overlap: true,
    filler_words: ["那个", "然后"],
    error_trigger_words: ["不对", "口误"],
    export_fade_duration: 0,
    export_transition_mode: "cut",
    export_video_codec: "libx264",
    export_audio_codec: "aac",
    export_audio_bitrate: "192k",
    export_preset: "medium",
    export_crf: 23,
    export_resolution: "original",
    export_ffmpeg_transitions: false,
    export_ffmpeg_fade_duration: 0,
    export_ffmpeg_fade_mode: "crossfade",
    asr_engine: "faster-whisper",
    asr_plugin_id: "demo-engine",
    asr_model_size: "base",
    asr_language: "zh",
    asr_device: "auto",
    asr_compute_type: "float32",
    asr_vad_filter: true,
    whisper_compute_type: "int8",
    qwen_compute_type: "float32",
    whisper_vad_threshold: 0.5,
    whisper_vad_min_silence_ms: 500,
    duplicate_threshold: 0.9,
    duplicate_min_length: 1,
    model_dir: "",
    proxy_resolution: "720p",
    auto_generate_proxy: false,
    llm_provider: "custom",
    llm_base_url: "demo://llm",
    llm_api_key: "demo",
    llm_model: "Milo Demo LLM",
    llm_temperature: 0.1,
    llm_timeout: 30,
    llm_thinking_enabled: true,
    llm_provider_configs: {
      custom: { base_url: "demo://llm", api_key: "demo", model: "Milo Demo LLM" },
    },
    llm_smart_batch_size: 20,
    llm_smart_overlap_size: 2,
    llm_correction_batch_size: 20,
    llm_correction_context_window: 2,
    llm_highlight_chunk_duration: 60,
    llm_highlight_overlap_duration: 5,
    llm_concurrency: 1,
    llm_max_batch_chars: 4000,
    llm_allow_local_urls: false,
  }
}

export async function callDemo<T = unknown>(method: string, ...args: unknown[]): Promise<ApiResponse<T>> {
  switch (method) {
    case "get_app_info": return ok({ version: "2.4.0-demo", demo: true } as T)
    case "get_recent_projects": return ok([] as T)
    case "get_project": return ok(demoStore.getProject() as T)
    case "switch_timeline": return ok(demoStore.getProject() as T)
    case "get_settings": return ok(getDemoSettings() as T)
    case "list_plugins": return ok([{ plugin_id: "demo-engine", display_name: "模拟 ASR 引擎", engine: "faster-whisper", version: "demo", status: "installed", installed_at: "", venv_path: "" }] as T)
    case "list_models": return ok([{ model_id: "demo-model", display_name: "演示模型", plugin_id: "demo-engine", engine: "faster-whisper", size_bytes: 0, local_path: "demo://model", status: "downloaded" }] as T)
    case "get_llm_config": return ok({ model: "Milo Demo LLM", base_url: "demo://llm", api_key_masked: "demo" } as T)
    case "get_waveform_url": return unsupported<T>()
    case "get_video_url": return unsupported<T>()
    case "update_segment": {
      const [segmentId, field, value] = args as [string, "start" | "end", number]
      return ok(demoStore.updateSegment(segmentId, field, value) as T)
    }
    case "update_segment_text": return ok(demoStore.updateSegmentText(args[0] as string, args[1] as string) as T)
    case "update_edit_decision": return ok(demoStore.setEditStatus(args[0] as string, args[1] as EditDecision["status"]) as T)
    case "update_edit_decisions_batch": return ok(demoStore.setEditStatuses(args[0] as string[], args[1] as EditDecision["status"]) as T)
    case "mark_segments": return ok(demoStore.addSmartDeleteEdits() as T)
    case "get_edit_summary": return ok(demoStore.getEditSummary() as T)
    case "get_subtitle_corrections": return ok(demoStore.getCorrections() as T)
    case "accept_correction": return ok({ segment_id: demoStore.getCorrections().find((item) => item.id === args[0])?.segment_id ?? "", project: demoStore.acceptCorrection(args[0] as string) } as T)
    case "reject_correction": return ok({ segment_id: demoStore.getCorrections().find((item) => item.id === args[0])?.segment_id ?? "", project: demoStore.rejectCorrection(args[0] as string) } as T)
    case "accept_high_confidence_corrections": return ok(demoStore.acceptHighConfidenceCorrections(Number(args[1] ?? 0.8)) as T)
    case "clear_subtitle_corrections": return ok(demoStore.clearCorrections() as T)
    case "compute_diff": return ok({ tokens: [{ text: String(args[0] ?? ""), type: "removed" }, { text: String(args[1] ?? ""), type: "added" }] } as T)
    case "create_task": return ok(createDemoTask(args[0] as string, (args[1] as Record<string, unknown>) ?? {}) as T)
    case "start_task": return ok(startDemoTask(args[0] as string) as T)
    case "cancel_task": cancelDemoTask(args[0] as string); return ok(undefined as T)
    case "get_task": return ok(demoStore.getTask(args[0] as string) as T)
    case "list_tasks": return ok(demoStore.getTasks() as T)
    case "start_smart_delete": return ok(startDemoLlmTask("llm_smart_delete") as T)
    case "start_subtitle_correction": return ok(startDemoLlmTask("llm_subtitle_correction") as T)
    case "start_highlight": return ok(startDemoLlmTask("llm_highlight") as T)
    case "cancel_llm_tasks": cancelDemoTask(); return ok(undefined as T)
    case "get_workflows": return ok(demoStore.getWorkflow() as T)
    case "save_workflow": {
      const workflow = { id: (args[2] as string) || `demo-workflow-${Date.now()}`, name: args[0] as string, steps: args[1] as never, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
      return ok(demoStore.saveWorkflow(workflow) as T)
    }
    case "delete_workflow": demoStore.deleteWorkflow(args[0] as string); return ok(undefined as T)
    case "start_workflow": return startDemoWorkflow(args[0] as string) as ApiResponse<T>
    case "cancel_workflow": demoStore.cancelWorkflow(); resetDemoTasks(); emitDemoEvent("workflow:cancelled", { completed_steps: 0 }); return ok(undefined as T)
    case "get_workflow_status": return ok({ active: demoStore.state.workflowSession?.status === "running", status: demoStore.state.workflowSession?.status ?? "idle", step_results: [] } as T)
    case "detect_workflow_conflicts": return ok({ conflicts: [], total_conflicts: 0 } as T)
    case "resolve_workflow_conflict": demoStore.resolveConflict(args[0] as string, args[1] as "keep_first" | "keep_last" | "keep_all"); emitDemoEvent(EVENT_DEMO_PROJECT_UPDATED, demoStore.getProject()); return ok(demoStore.getProject() as T)
    case "apply_workflow": demoStore.finishWorkflow(); emitDemoEvent(EVENT_DEMO_PROJECT_UPDATED, demoStore.getProject()); return ok(demoStore.getProject() as T)
    case "discard_workflow": demoStore.reset(); return ok(demoStore.getProject() as T)
    case "update_settings": return ok({} as T)
    case "save_project": return ok(undefined as T)
    case "close_project": return ok(undefined as T)
    case "export_video":
    case "export_audio":
    case "export_subtitle":
    case "export_vtt": return ok(undefined as T)
    case "test_llm_connection": return ok({ success: true, message: "演示连接已就绪" } as T)
    case "get_llm_prompts": return ok([] as T)
    case "get_prompt_presets": return ok([] as T)
    default: return unsupported<T>()
  }
}

export function resetDemoRuntime() {
  resetDemoTasks()
  demoStore.reset()
  emitDemoEvent(EVENT_DEMO_RESET, { project: demoStore.getProject() })
}
