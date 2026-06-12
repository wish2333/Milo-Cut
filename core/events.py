"""Event name constants for bridge communication.

Must stay in sync with frontend src/utils/events.ts.
"""

# Task lifecycle
TASK_PROGRESS = "task:progress"
TASK_COMPLETED = "task:completed"
TASK_FAILED = "task:failed"

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
