"""Event name constants for bridge communication.

Must stay in sync with frontend src/utils/events.ts.
"""

# Task lifecycle
TASK_PROGRESS = "task:progress"
TASK_COMPLETED = "task:completed"
TASK_FAILED = "task:failed"
TASK_CANCELLED = "task:cancelled"

# Project-level
PROJECT_SAVED = "project:saved"
PROJECT_DIRTY = "project:dirty"

# Analysis results
ANALYSIS_UPDATED = "analysis:updated"

# Edit summary
EDIT_SUMMARY_UPDATED = "edit:summary_updated"

# Log forwarding
LOG_LINE = "log_line"

# Encoder fallback
ENCODER_FALLBACK = "encoder:fallback"

# LLM analysis
LLM_ANALYSIS_PROGRESS = "llm:analysis_progress"
LLM_ANALYSIS_COMPLETED = "llm:analysis_completed"
LLM_ANALYSIS_FAILED = "llm:analysis_failed"
LLM_TOKEN_USAGE = "llm:token_usage"

# P0: Smart delete
LLM_SMART_DELETE_PROGRESS = "llm:smart_delete_progress"
LLM_SMART_DELETE_COMPLETED = "llm:smart_delete_completed"

# P1: Subtitle correction
LLM_SUBTITLE_CORRECTION_COMPLETED = "llm:subtitle_correction_completed"

# P2: Highlight extraction
LLM_HIGHLIGHT_PROGRESS = "llm:highlight_progress"
LLM_HIGHLIGHT_COMPLETED = "llm:highlight_completed"

# P3: Semantic search
LLM_SEMANTIC_SEARCH_COMPLETED = "llm:semantic_search_completed"

# Workflow (v2.1.0 Phase 3)
WORKFLOW_STARTED = "workflow:started"
WORKFLOW_STEP_STARTED = "workflow:step_started"
WORKFLOW_STEP_PROGRESS = "workflow:step_progress"
WORKFLOW_STEP_COMPLETED = "workflow:step_completed"
WORKFLOW_STEP_FAILED = "workflow:step_failed"
WORKFLOW_COMPLETED = "workflow:completed"
WORKFLOW_CANCELLED = "workflow:cancelled"
WORKFLOW_CONFLICTS_DETECTED = "workflow:conflicts_detected"
WORKFLOW_HEARTBEAT = "workflow:heartbeat"
