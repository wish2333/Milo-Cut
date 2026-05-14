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
