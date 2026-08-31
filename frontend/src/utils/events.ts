export const EVENT_TASK_PROGRESS = "task:progress"
export const EVENT_TASK_COMPLETED = "task:completed"
export const EVENT_TASK_FAILED = "task:failed"
export const EVENT_TASK_CANCELLED = "task:cancelled"

export const EVENT_PROJECT_SAVED = "project:saved"
export const EVENT_PROJECT_DIRTY = "project:dirty"

export const EVENT_EDIT_SUMMARY_UPDATED = "edit:summary_updated"

export const EVENT_LOG_LINE = "log_line"

export const EVENT_ENCODER_FALLBACK = "encoder:fallback"

// LLM analysis
export const EVENT_LLM_ANALYSIS_PROGRESS = "llm:analysis_progress"
export const EVENT_LLM_ANALYSIS_COMPLETED = "llm:analysis_completed"
export const EVENT_LLM_ANALYSIS_FAILED = "llm:analysis_failed"
export const EVENT_LLM_TOKEN_USAGE = "llm:token_usage"

// P0: Smart delete
export const EVENT_LLM_SMART_DELETE_PROGRESS = "llm:smart_delete_progress"
export const EVENT_LLM_SMART_DELETE_COMPLETED = "llm:smart_delete_completed"

// P1: Subtitle correction
export const EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED = "llm:subtitle_correction_completed"

// P2: Highlight extraction
export const EVENT_LLM_HIGHLIGHT_PROGRESS = "llm:highlight_progress"
export const EVENT_LLM_HIGHLIGHT_COMPLETED = "llm:highlight_completed"

// P3: Semantic search
export const EVENT_LLM_SEMANTIC_SEARCH_COMPLETED = "llm:semantic_search_completed"

// Workflow (v2.1.0 Phase 3)
export const EVENT_WORKFLOW_STARTED = "workflow:started"
export const EVENT_WORKFLOW_STEP_STARTED = "workflow:step_started"
export const EVENT_WORKFLOW_STEP_PROGRESS = "workflow:step_progress"
export const EVENT_WORKFLOW_STEP_COMPLETED = "workflow:step_completed"
export const EVENT_WORKFLOW_STEP_FAILED = "workflow:step_failed"
export const EVENT_WORKFLOW_COMPLETED = "workflow:completed"
export const EVENT_WORKFLOW_CANCELLED = "workflow:cancelled"
// v3.0.0 M3-6: failure rollback finished (layers restored via apply_undo)
export const EVENT_WORKFLOW_ROLLED_BACK = "workflow:rolled_back"
export const EVENT_WORKFLOW_CONFLICTS_DETECTED = "workflow:conflicts_detected"
export const EVENT_WORKFLOW_HEARTBEAT = "workflow:heartbeat"

// Browser demo runtime lifecycle
export const EVENT_DEMO_RESET = "demo:reset"
export const EVENT_DEMO_PROJECT_UPDATED = "demo:project_updated"
