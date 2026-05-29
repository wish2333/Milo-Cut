# ASR GUI Issues Fix Plan (v1.2.0 Audit Report)

## TL;DR

> **Quick Summary**: Fix 8 transcription GUI issues from audit-report-1.2.0-2: per-engine settings persistence, device filtering by pluginId, SRT import after transcription, auto-language support, cleanup confirm dialogs, VAD parameter configuration, and inference precision defaults.
> 
> **Deliverables**:
> - Per-engine ASR settings with engine-prefixed fields in settings.json
> - Device dropdown filtered by pluginId (GPU option only for GPU plugins)
> - SRT auto-generated and imported into project after transcription
> - Auto-detect language option for Qwen3-ASR
> - Confirmation dialogs for destructive cleanup operations
> - VAD threshold and min_silence_duration_ms configuration UI
> - Correct inference precision defaults (Whisper: int8_float16, Qwen: bfloat16)
> - Backend test suite covering all 8 issues
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Task 1 (config defaults) -> Task 3 (frontend load/save) -> Task 6 (integration test)

---

## Context

### Original Request
Fix 8 GUI issues identified in the third-round audit report (docs/1.2.0/audit-report-1.2.0-2.md) for Milo-Cut's ASR transcription feature.

### Interview Summary
**Key Discussions**:
- Audit report provided exact root cause analysis for all 8 issues with precise code locations
- Architecture decision: flat dictionary with engine-prefixed keys (whisper_*/qwen_*) rather than nested dicts
- Test strategy: pytest for backend logic, tests cover all 12 scenarios from the audit report

**Research Findings**:
- `get_data_dir` IS imported inline at main.py:319, but NOT at module scope (works but inconsistent)
- `cleanup_tasks_folder` is DUPLICATED at lines 921 and 939 (second shadows first)
- `_handle_transcription` already auto-saves SRT to data/transcripts/ but does NOT import it back into project
- `qwen_transcribe.py:378` uses `torch.float16` (should be `torch.bfloat16`)
- `whisper_transcribe.py` has no `vad_parameters` passthrough
- Both backend scripts don't handle "auto" language properly

### Key Gaps Addressed
- Report's Issue 6 stated `get_data_dir` not imported -- partially outdated, it IS imported inline but inconsistently
- Duplicate `cleanup_tasks_folder` method is an additional bug not explicitly listed as a separate issue
- Qwen3 ignores `compute_type` setting entirely -- needs a `--compute-type` CLI arg added

---

## Work Objectives

### Core Objective
Fix all 8 ASR GUI issues so that transcription settings persist per-engine, device options reflect plugin capabilities, SRT is automatically imported, language auto-detection works, destructive operations have confirmation dialogs, VAD parameters are configurable, and inference precision uses correct defaults.

### Concrete Deliverables
- `core/config.py` with expanded engine-prefixed default settings
- `main.py` with fixed per-engine settings read, SRT import, duplicate cleanup removal
- `core/asr_scripts/qwen_transcribe.py` with bfloat16 default and auto-language handling
- `core/asr_scripts/whisper_transcribe.py` with vad_parameters passthrough
- `frontend/src/pages/WorkspacePage.vue` with per-engine load/save, device filtering, compute_type dropdowns, VAD sliders, auto-language option
- `frontend/src/components/workspace/SettingsModal.vue` with confirmation dialogs
- `tests/test_asr_gui_e2e.py` with 12 test cases

### Definition of Done
- [ ] `uv run pytest tests/test_asr_gui_e2e.py -v` passes all 12 tests
- [ ] `cd frontend && bun run build` succeeds (no TypeScript errors)
- [ ] Per-engine settings survive save/reload and engine switching
- [ ] CPU plugins cannot select CUDA device
- [ ] Transcription generates SRT and imports it into project
- [ ] Auto-detect language option works for both engines

### Must Have
- Per-engine settings persistence with engine-prefixed flat keys
- Device dropdown filtered by pluginId (GPU only for GPU plugins)
- SRT auto-import after transcription with correct project state returned
- "Auto-detect" language option mapping to None for both engines
- Confirmation dialogs before cleanup operations
- VAD threshold and min_silence_duration_ms configurable
- Whisper default compute_type: int8_float16
- Qwen default dtype: bfloat16
- All 12 backend test cases passing

### Must NOT Have (Guardrails)
- Do NOT introduce nested dict settings structure (use flat engine-prefixed keys)
- Do NOT change the existing `export_srt()` function signature
- Do NOT modify any non-ASR related settings or UI
- Do NOT add emoji to code or commit messages
- Do NOT use bare `python` -- use `uv run` for all Python execution
- Do NOT break existing faster-whisper or qwen3-asr transcription flows
- Do NOT remove the existing auto-save SRT to data/transcripts/ feature
- Do NOT add new pip/conda dependencies

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest + vitest)
- **Automated tests**: Tests-after (implementation first, then test verification)
- **Framework**: pytest (backend), vitest (frontend)
- **Test file**: `tests/test_asr_gui_e2e.py` (new, 12 test cases)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.omo/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend logic**: Use Bash (`uv run pytest`) - Run specific tests, assert pass/fail
- **Frontend build**: Use Bash (`cd frontend && bun run build`) - Assert zero errors
- **Config validation**: Use Bash (`uv run python -c "..."`) - Import and assert defaults

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately - backend foundation):
+--- Task 1: Expand config.py defaults with engine-prefixed fields [quick]
+--- Task 2: Fix qwen_transcribe.py dtype + language + compute_type [quick]
+--- Task 3: Fix whisper_transcribe.py vad_parameters + language [quick]

Wave 2 (After Wave 1 - frontend + main.py integration):
+--- Task 4: Rewrite WorkspacePage.vue load/save with per-engine logic [unspecified-high]
    depends: 1
+--- Task 5: Fix main.py _handle_transcription SRT import + cleanup duplicate + settings read [unspecified-high]
    depends: 1, 2, 3
+--- Task 6: Add confirmation dialogs to SettingsModal.vue [quick]
    (independent, can run in parallel with 4 and 5)

Wave 3 (After Wave 2 - testing + verification):
+--- Task 7: Write backend test suite (12 test cases) [unspecified-high]
    depends: 1, 2, 3, 4, 5
+--- Task 8: Frontend TypeScript build verification [quick]
    depends: 4, 6

Wave FINAL (After ALL tasks):
+--- F1. Plan compliance audit (oracle)
+--- F2. Code quality review (unspecified-high)
+--- F3. Real manual QA (unspecified-high)
+--- F4. Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: Task 1 -> Task 4 -> Task 7
Parallel Speedup: ~50% faster than sequential
Max Concurrent: 3 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | - | 4, 5, 7 | 1 |
| 2 | - | 5, 7 | 1 |
| 3 | - | 5, 7, 8 | 1 |
| 4 | 1 | 7, 8 | 2 |
| 5 | 1, 2, 3 | 7 | 2 |
| 6 | - | 8 | 2 |
| 7 | 1, 2, 3, 4, 5 | F1-F4 | 3 |
| 8 | 4, 6 | F1-F4 | 3 |

### Agent Dispatch Summary

- **Wave 1**: 3 agents - T1 `quick`, T2 `quick`, T3 `quick`
- **Wave 2**: 3 agents - T4 `unspecified-high`, T5 `unspecified-high`, T6 `quick`
- **Wave 3**: 2 agents - T7 `unspecified-high`, T8 `quick`
- **FINAL**: 4 agents - F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

- [ ] 1. Expand config.py defaults with engine-prefixed fields

  **What to do**:
  - Add per-engine settings keys to `_DEFAULT_SETTINGS` dict in `core/config.py:14-52` using flat engine-prefixed naming convention
  - New keys to add after line 49 (`"asr_vad_filter": True,`):
    - `"whisper_compute_type": "int8_float16"` (fixes incorrect default "int8")
    - `"whisper_vad_threshold": 0.5`
    - `"whisper_vad_min_silence_ms": 500`
    - `"qwen_compute_type": "bfloat16"`
    - `"qwen_language": "auto"` (separate from whisper language default)
  - Keep existing `asr_engine`, `asr_model_size`, `asr_device` as shared keys
  - Remove old generic `"asr_compute_type": "int8"` (replaced by engine-specific versions)
  - Verify `load_settings()` still returns correct merged dict with new defaults

  **Must NOT do**:
  - Do NOT create nested dicts (e.g. `{"whisper": {"compute_type": ...}}`)
  - Do NOT modify any non-ASR settings
  - Do NOT change the `load_settings()` or `save_settings()` function signatures

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single file, well-defined dict addition, no complex logic
  - **Skills**: [`python-patterns`]
    - `python-patterns`: Dict patterns and type hints for the settings dict
  - **Skills Evaluated but Omitted**:
    - `tdd-workflow`: No test-first needed for config defaults; tests come in Task 7

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: Tasks 4, 5, 7
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References** (existing code to follow):
  - `core/config.py:14-52` - Current `_DEFAULT_SETTINGS` dict structure. Follow exact same key-value style, no nesting.
  - `core/config.py:55-74` - `load_settings()` and `save_settings()` functions. Verify they still work with new keys.

  **API/Type References** (contracts to implement against):
  - `main.py:392-404` - How `_handle_transcription` reads settings with `settings.get("asr_compute_type", "int8")`. These calls will be updated in Task 5 to use new engine-prefixed keys.
  - `frontend/src/pages/WorkspacePage.vue:103-124` - Frontend `asrSettingsPerEngine` reactive object that will consume these settings.

  **WHY Each Reference Matters**:
  - `config.py:14-52`: This is THE file to modify. Copy existing style exactly.
  - `main.py:392-404`: Shows the current key names being consumed. Task 5 will update these to match new prefixed keys.
  - `WorkspacePage.vue:103-124`: Shows frontend expects specific key names. Must align naming.

  **Acceptance Criteria**:

  - [ ] `core/config.py` contains keys: `whisper_compute_type`, `whisper_vad_threshold`, `whisper_vad_min_silence_ms`, `qwen_compute_type`, `qwen_language`
  - [ ] `uv run python -c "from core.config import _DEFAULT_SETTINGS; d=_DEFAULT_SETTINGS; assert d['whisper_compute_type']=='int8_float16'; assert d['qwen_compute_type']=='bfloat16'; assert d['qwen_language']=='auto'; assert 'asr_compute_type' not in d"` passes
  - [ ] `uv run python -c "from core.config import load_settings; s=load_settings(); assert s['whisper_compute_type']=='int8_float16'"` passes

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Config defaults contain all engine-prefixed keys with correct values
    Tool: Bash (uv run python -c)
    Preconditions: core/config.py exists, no settings.json overrides
    Steps:
      1. Run: uv run python -c "from core.config import _DEFAULT_SETTINGS as d; keys=['whisper_compute_type','whisper_vad_threshold','whisper_vad_min_silence_ms','qwen_compute_type','qwen_language']; assert all(k in d for k in keys), f'Missing: {[k for k in keys if k not in d]}'; assert d['whisper_compute_type']=='int8_float16'; assert d['qwen_compute_type']=='bfloat16'; assert d['qwen_language']=='auto'; assert d['whisper_vad_threshold']==0.5; assert d['whisper_vad_min_silence_ms']==500; print('ALL KEYS PRESENT AND CORRECT')"
    Expected Result: stdout contains "ALL KEYS PRESENT AND CORRECT"
    Failure Indicators: AssertionError or KeyError
    Evidence: .omo/evidence/task-1-config-defaults.txt

  Scenario: Old generic asr_compute_type key removed
    Tool: Bash (uv run python -c)
    Preconditions: core/config.py modified
    Steps:
      1. Run: uv run python -c "from core.config import _DEFAULT_SETTINGS as d; assert 'asr_compute_type' not in d, 'Old generic key still present'; print('OLD KEY REMOVED')"
    Expected Result: stdout contains "OLD KEY REMOVED"
    Failure Indicators: AssertionError "Old generic key still present"
    Evidence: .omo/evidence/task-1-old-key-removed.txt
  ```

  **Commit**: YES (groups with 2, 3)
  - Message: `fix(asr): engine-prefixed settings defaults + dtype/compute_type fixes + vad_parameters`
  - Files: `core/config.py`
  - Pre-commit: `uv run python -c "from core.config import load_settings; load_settings()"`

- [ ] 2. Fix qwen_transcribe.py: dtype, language auto-detect, compute_type CLI arg

  **What to do**:
  - Change `torch.float16` to `torch.bfloat16` at `core/asr_scripts/qwen_transcribe.py:378`
  - Add auto-language handling: when `--language` is `"auto"`, `""`, or `"None"`, pass `None` to `model.transcribe()` instead of the string. Add this conversion near lines 410-423 where language is currently processed.
  - Add `--compute-type` CLI argument to the argparse section. Currently the script ignores compute_type entirely. Add argument `--compute-type` with default `"bfloat16"`, then use it to set `torch_dtype` at line 378: `torch_dtype=getattr(torch, args.compute_type.replace("float", "float"))` or a mapping dict `{"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}`.
  - Ensure backward compatibility: if `--compute-type` not provided, default to `bfloat16`.

  **Must NOT do**:
  - Do NOT change the script's output format (JSON structure)
  - Do NOT remove existing CLI arguments
  - Do NOT add external dependencies

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 3 focused changes in a single file, well-scoped
  - **Skills**: [`python-patterns`]
    - `python-patterns`: Argparse patterns and dict mapping for dtype conversion
  - **Skills Evaluated but Omitted**:
    - `python-testing`: Tests come in Task 7, not here

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References** (existing code to follow):
  - `core/asr_scripts/qwen_transcribe.py:378` - Current `torch.float16` dtype assignment. Change to `torch.bfloat16` or use compute_type mapping.
  - `core/asr_scripts/qwen_transcribe.py:410-423` - Language processing logic. Add `if raw_lang in ["auto", "", "None", None]: lang = None` before current processing.
  - `core/asr_scripts/whisper_transcribe.py:60-90` - Reference for how whisper script handles argparse and compute_type. Follow similar pattern for adding `--compute-type`.

  **API/Type References** (contracts to implement against):
  - `main.py:419-434` - How main.py calls `transcribe_with_qwen()`. Note it does NOT pass compute_type currently. Task 5 will add this.
  - `core/asr_service.py` - The service layer that invokes this script via subprocess. Check how CLI args are constructed.

  **WHY Each Reference Matters**:
  - `qwen_transcribe.py:378`: Exact line to change dtype.
  - `qwen_transcribe.py:410-423`: Where language auto-detect logic goes.
  - `whisper_transcribe.py:60-90`: Pattern to copy for compute_type CLI arg.

  **Acceptance Criteria**:

  - [ ] `qwen_transcribe.py` line ~378 uses `torch.bfloat16` as default dtype (not `torch.float16`)
  - [ ] `--compute-type` argument added to argparse with default `"bfloat16"`
  - [ ] Language `"auto"` / `""` / `"None"` maps to `None` passed to `model.transcribe()`
  - [ ] `grep -n "float16\|float32\|bfloat16" core/asr_scripts/qwen_transcribe.py` shows bfloat16 as default

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Default dtype is bfloat16, not float16
    Tool: Bash (grep + uv run python -c)
    Preconditions: qwen_transcribe.py modified
    Steps:
      1. Run: grep -n "torch.bfloat16\|torch.float16\|torch.float32" core/asr_scripts/qwen_transcribe.py
      2. Assert: "torch.bfloat16" appears in the dtype mapping or default assignment
      3. Assert: No standalone "torch.float16" remains as the unconditional default
    Expected Result: bfloat16 is the default, float16 only in mapping dict
    Failure Indicators: "torch.float16" at the default assignment line
    Evidence: .omo/evidence/task-2-dtype-check.txt

  Scenario: --compute-type CLI argument exists with bfloat16 default
    Tool: Bash (grep)
    Preconditions: qwen_transcribe.py modified
    Steps:
      1. Run: grep -n "compute.type\|compute_type" core/asr_scripts/qwen_transcribe.py
      2. Assert: argparse section has "--compute-type" with default containing "bfloat16"
    Expected Result: grep shows compute-type argument definition
    Failure Indicators: No --compute-type found in argparse
    Evidence: .omo/evidence/task-2-compute-type-arg.txt

  Scenario: Auto-language maps to None
    Tool: Bash (grep)
    Preconditions: qwen_transcribe.py modified
    Steps:
      1. Run: grep -n -A2 "auto\|None" core/asr_scripts/qwen_transcribe.py | head -30
      2. Assert: Logic exists to convert "auto"/""/"None" to Python None
    Expected Result: Conditional mapping "auto" -> None present
    Failure Indicators: No auto-detect logic found
    Evidence: .omo/evidence/task-2-auto-language.txt
  ```

  **Commit**: YES (groups with 1, 3)
  - Message: `fix(asr): engine-prefixed settings defaults + dtype/compute_type fixes + vad_parameters`
  - Files: `core/asr_scripts/qwen_transcribe.py`

- [ ] 3. Fix whisper_transcribe.py: vad_parameters passthrough + language auto-detect

  **What to do**:
  - Add `--vad-threshold` and `--vad-min-silence-ms` CLI arguments to argparse section (near line 60-90)
  - Pass these as `vad_parameters` dict to the whisper transcribe call. Currently `vad_filter=True` is passed at line ~110 but no `vad_parameters` dict.
  - Add `vad_parameters={"vad_onset": float(args.vad_threshold), "vad_min_silence_duration_ms": int(args.vad_min_silence_ms)}` when `vad_filter` is True
  - Add auto-language handling: when `--language` is `"auto"`, `""`, or `"None"`, omit the `language` parameter from the transcribe call entirely (faster-whisper auto-detects when language is not specified)
  - Default `--compute-type` should remain `"int8_float16"` (already correct in whisper script at line ~68, but verify)

  **Must NOT do**:
  - Do NOT change the script's JSON output format
  - Do NOT modify existing `--compute-type` behavior if it already works correctly
  - Do NOT add external dependencies

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Focused additions to argparse and transcribe call in single file
  - **Skills**: [`python-patterns`]
    - `python-patterns`: Argparse and dict construction patterns
  - **Skills Evaluated but Omitted**:
    - `python-testing`: Tests come in Task 7

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Tasks 5, 7, 8
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References** (existing code to follow):
  - `core/asr_scripts/whisper_transcribe.py:60-90` - Argparse section. Add `--vad-threshold` (float, default 0.5) and `--vad-min-silence-ms` (int, default 500) here.
  - `core/asr_scripts/whisper_transcribe.py:110` - Current `vad_filter` parameter. Add `vad_parameters` dict next to it.
  - `core/asr_scripts/whisper_transcribe.py:68` - `--compute-type` argument. Verify default is `int8_float16`.

  **API/Type References** (contracts to implement against):
  - `main.py:398-418` - How main.py constructs whisper CLI invocation. Task 5 will add vad_threshold/vad_min_silence_ms to the payload.
  - `core/asr_service.py` - Service layer that invokes this script. Check how `vad_filter` is currently passed.

  **WHY Each Reference Matters**:
  - `whisper_transcribe.py:60-90`: Where to add new argparse args.
  - `whisper_transcribe.py:110`: Where to inject vad_parameters into transcribe call.
  - `whisper_transcribe.py:68`: Verify compute_type default is correct.

  **Acceptance Criteria**:

  - [ ] `--vad-threshold` and `--vad-min-silence-ms` arguments added to argparse
  - [ ] `vad_parameters` dict passed to transcribe call when `vad_filter=True`
  - [ ] Language `"auto"` / `""` / `"None"` causes `language` param to be omitted from transcribe call
  - [ ] `grep -n "vad_threshold\|vad_min_silence\|vad_parameters" core/asr_scripts/whisper_transcribe.py` shows all three

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: VAD CLI arguments exist with correct defaults
    Tool: Bash (grep)
    Preconditions: whisper_transcribe.py modified
    Steps:
      1. Run: grep -n "vad.threshold\|vad.min.silence" core/asr_scripts/whisper_transcribe.py
      2. Assert: Both "--vad-threshold" (default 0.5) and "--vad-min-silence-ms" (default 500) appear in argparse
    Expected Result: Two new argparse arguments found
    Failure Indicators: grep returns empty or missing argument
    Evidence: .omo/evidence/task-3-vad-args.txt

  Scenario: vad_parameters dict passed to transcribe
    Tool: Bash (grep)
    Preconditions: whisper_transcribe.py modified
    Steps:
      1. Run: grep -n "vad_parameters" core/asr_scripts/whisper_transcribe.py
      2. Assert: vad_parameters dict with "vad_onset" and "vad_min_silence_duration_ms" is constructed and passed
    Expected Result: vad_parameters dict visible in transcribe call context
    Failure Indicators: No vad_parameters found
    Evidence: .omo/evidence/task-3-vad-params.txt

  Scenario: Auto-language omits language parameter
    Tool: Bash (grep)
    Preconditions: whisper_transcribe.py modified
    Steps:
      1. Run: grep -n -B2 -A2 "language" core/asr_scripts/whisper_transcribe.py | grep -i "auto\|None\|omit"
      2. Assert: Logic exists to skip language param when value is "auto"/""
    Expected Result: Conditional language omission found
    Failure Indicators: No auto-detect logic
    Evidence: .omo/evidence/task-3-auto-language.txt
  ```

  **Commit**: YES (groups with 1, 2)
  - Message: `fix(asr): engine-prefixed settings defaults + dtype/compute_type fixes + vad_parameters`
  - Files: `core/asr_scripts/whisper_transcribe.py`

- [ ] 4. Rewrite WorkspacePage.vue load/save with per-engine settings + device filtering + compute_type dropdowns + VAD sliders

  **What to do**:
  - In `frontend/src/pages/WorkspacePage.vue`:
    1. **Rewrite `loadAsrSettings()`** (~line 303): Read engine-prefixed keys from settings (e.g. `whisper_compute_type`, `qwen_compute_type`) instead of generic `asr_compute_type`. Map them into `asrSettingsPerEngine` reactive object with two engines (`faster-whisper` and `qwen3-asr`), each having: `modelSize`, `computeType`, `vadFilter`, `vadThreshold`, `vadMinSilenceMs`, `alignerModelSize` (qwen only).
    2. **Rewrite `saveAsrSettings()`** (~line 317): Save engine-prefixed keys back to settings via bridge call. Write flat keys like `whisper_compute_type`, `qwen_compute_type`, etc.
    3. **Add device filtering by pluginId**: In the device dropdown (line ~778), filter available GPU options based on the selected plugin's capabilities. If the plugin is CPU-only (e.g., `pluginId` does not contain GPU indicators), hide or disable the CUDA device option.
    4. **Add compute_type dropdowns**: For each engine, add a `<select>` for compute type with engine-appropriate options:
       - Whisper: `int8`, `int8_float16`, `float16`, `float32`
       - Qwen: `bfloat16`, `float16`, `float32`
    5. **Add VAD sliders**: Add range inputs for `vadThreshold` (0.0-1.0, step 0.05) and `vadMinSilenceMs` (100-2000ms, step 50). Only visible when `vadFilter` is true.
    6. **Add "Auto-detect" language option**: Add "Auto-detect" to language dropdown, map to `"auto"` value.

  **Must NOT do**:
  - Do NOT change the bridge API contract (still uses `call("save_settings", ...)`)
  - Do NOT add new Vue Router routes or pages
  - Do NOT modify non-ASR UI sections
  - Do NOT add emoji to UI labels

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`frontend-patterns`, `coding-standards`]
    - `frontend-patterns`: Vue 3 Composition API patterns, reactive state management
    - `coding-standards`: TypeScript conventions, component structure

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6)
  - **Blocks**: Tasks 7, 8
  - **Blocked By**: Task 1 (needs engine-prefixed keys in config)

  **References**:

  **Pattern References**:
  - `frontend/src/pages/WorkspacePage.vue:103-124` - Current `asrSettingsPerEngine` reactive state definition. Needs restructuring to hold per-engine fields.
  - `frontend/src/pages/WorkspacePage.vue:303-317` - `loadAsrSettings()` function. Reads generic `asr_compute_type`, `asr_vad_filter` etc. Must be rewritten to read engine-prefixed keys.
  - `frontend/src/pages/WorkspacePage.vue:770-800` - ASR settings UI section with device dropdown, model size input, compute type input (currently text, needs dropdown).

  **API/Type References**:
  - `main.py:520-550` - `get_settings` expose method. Returns full settings dict. Frontend reads from this.
  - `main.py:560-580` - `save_settings` expose method. Accepts partial settings dict to merge.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Per-engine settings load correctly
    Tool: Bash (frontend build check)
    Preconditions: WorkspacePage.vue is saved
    Steps:
      1. Run: cd frontend && bun run build 2>&1 | tail -5
      2. Assert: Build succeeds with no TypeScript errors
    Expected Result: Build completes with exit code 0
    Failure Indicators: TypeScript errors, build failure
    Evidence: .omo/evidence/task-4-build.txt

  Scenario: Device dropdown filters by pluginId
    Tool: Bash (grep)
    Preconditions: WorkspacePage.vue is saved
    Steps:
      1. Run: grep -n "pluginId\|plugin.*device\|isGpu\|cuda" frontend/src/pages/WorkspacePage.vue | head -10
      2. Assert: Device filtering logic references plugin capabilities
    Expected Result: grep shows plugin-aware device filtering
    Failure Indicators: No pluginId reference in device dropdown logic
    Evidence: .omo/evidence/task-4-device-filter.txt

  Scenario: VAD sliders present in template
    Tool: Bash (grep)
    Preconditions: WorkspacePage.vue is saved
    Steps:
      1. Run: grep -n "vadThreshold\|vadMinSilence\|vad-threshold\|vad-min-silence" frontend/src/pages/WorkspacePage.vue | head -10
      2. Assert: VAD slider/template bindings exist
    Expected Result: VAD controls found in template
    Failure Indicators: No VAD threshold controls
    Evidence: .omo/evidence/task-4-vad-sliders.txt
  ```

  **Commit**: YES (groups with 6)
  - Message: `fix(asr): per-engine settings UI + device filtering + VAD sliders + confirm dialogs`
  - Files: `frontend/src/pages/WorkspacePage.vue`

- [ ] 5. Fix main.py: SRT import after transcription + cleanup duplicate + per-engine settings read

  **What to do**:
  - In `main.py`:
    1. **SRT auto-import** (after line 493): After the auto-save SRT section, add a call to `self.import_srt(srt_path)` to load the generated SRT back into the project as subtitle tracks. Use the existing `import_srt` method at `main.py:578` on the `MiloCutApi` class. Return the updated project state in the response.
    2. **Remove duplicate `cleanup_tasks_folder`** (lines 938-960): Delete the second `cleanup_tasks_folder` method (the one at line 938 that shadows the first at line 920). The first one at line 920 is the correct implementation.
    3. **Update `_handle_transcription` settings reads** (lines 394-404): Replace generic `settings.get("asr_compute_type", "int8")` with engine-prefixed reads: `settings.get("whisper_compute_type", "int8_float16")` for whisper, and pass `compute_type` to the qwen call (currently missing at line 425-434).
    4. **Pass VAD params to whisper**: In the whisper branch (line 407-418), pass `vad_threshold` and `vad_min_silence_ms` from settings to the CLI args.
    5. **Pass compute_type to qwen**: In the qwen branch (line 419-434), add `compute_type` parameter to `transcribe_with_qwen()` call.

  **Must NOT do**:
  - Do NOT change the `export_srt()` function signature
  - Do NOT remove the existing auto-save SRT to `data/transcripts/` feature
  - Do NOT modify the task manager or background task system
  - Do NOT change the `@expose` decorator behavior

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-patterns`]
    - `python-patterns`: Pydantic model patterns, async patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 6)
  - **Blocks**: Task 7
  - **Blocked By**: Tasks 1, 2, 3 (needs engine-prefixed config + fixed backend scripts)

  **References**:

  **Pattern References**:
  - `main.py:384-493` - `_handle_transcription` method. Lines 392-404 read settings. Lines 451-486 auto-save SRT. After line 486, add SRT import.
  - `main.py:920-936` - First `cleanup_tasks_folder` (keep this one).
  - `main.py:938-960` - Second `cleanup_tasks_folder` (DELETE this one -- it shadows the first).
  - `main.py:319` - Inline `get_data_dir` import. Move to top-level import for consistency.

  **API/Type References**:
  - `main.py:578` - `import_srt()` method on `MiloCutApi` class (not `project_service`). Call `self.import_srt(srt_path)` from within `_handle_transcription`.
  - `core/asr_service.py:transcribe_with_qwen()` - Verify it accepts `compute_type` parameter (or if the script handles it via CLI).
  - `core/config.py:14-52` - After Task 1, contains engine-prefixed defaults. `_handle_transcription` reads from here.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: SRT import call exists after auto-save
    Tool: Bash (grep)
    Preconditions: main.py is saved
    Steps:
      1. Run: grep -n "import_srt\|import.*srt" main.py | head -10
      2. Assert: import_srt call exists in _handle_transcription method
    Expected Result: import_srt call found after SRT auto-save section
    Failure Indicators: No import_srt reference in _handle_transcription
    Evidence: .omo/evidence/task-5-srt-import.txt

  Scenario: Only one cleanup_tasks_folder method exists
    Tool: Bash (grep)
    Preconditions: main.py is saved
    Steps:
      1. Run: grep -c "def cleanup_tasks_folder" main.py
      2. Assert: Count is exactly 1
    Expected Result: grep count returns "1"
    Failure Indicators: Count is 0 or 2+
    Evidence: .omo/evidence/task-5-cleanup-dedup.txt

  Scenario: Engine-prefixed settings reads
    Tool: Bash (grep)
    Preconditions: main.py is saved
    Steps:
      1. Run: grep -n "whisper_compute_type\|qwen_compute_type" main.py | head -10
      2. Assert: Engine-prefixed keys are read in _handle_transcription
    Expected Result: grep shows engine-prefixed settings reads
    Failure Indicators: Only generic asr_compute_type found
    Evidence: .omo/evidence/task-5-prefixed-reads.txt
  ```

  **Commit**: YES (standalone)
  - Message: `fix(asr): SRT import after transcription + cleanup duplicate method + per-engine settings read`
  - Files: `main.py`

- [ ] 6. Add confirmation dialogs to SettingsModal.vue cleanup calls

  **What to do**:
  - In `frontend/src/components/workspace/SettingsModal.vue`:
    1. **Line ~267**: Before the `cleanup_tasks_folder` bridge call, add a `window.confirm()` dialog: "Are you sure you want to clean up task files? This will delete all log and result files."
    2. **Line ~285**: Before the `cleanup_silence_detection` bridge call (or similar cleanup), add a `window.confirm()` dialog: "Are you sure you want to clean up silence detection data?"
    3. Only proceed with the cleanup if the user confirms (returns `true`).

  **Must NOT do**:
  - Do NOT change the cleanup backend logic
  - Do NOT add new cleanup operations
  - Do NOT modify non-cleanup UI sections
  - Do NOT use a custom modal component (use `window.confirm()` for simplicity)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`frontend-patterns`]
    - `frontend-patterns`: Vue event handler patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5)
  - **Blocks**: Task 8
  - **Blocked By**: None (independent of backend changes)

  **References**:

  **Pattern References**:
  - `frontend/src/components/workspace/SettingsModal.vue:260-290` - Cleanup button click handlers. Lines 267 and 285 make bridge calls directly without confirmation.
  - `frontend/src/components/workspace/SettingsModal.vue:1-30` - Component imports and structure.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: confirm() dialog exists before cleanup_tasks_folder
    Tool: Bash (grep)
    Preconditions: SettingsModal.vue is saved
    Steps:
      1. Run: grep -n "confirm\|window.confirm" frontend/src/components/workspace/SettingsModal.vue | head -10
      2. Assert: At least 2 confirm() calls exist (one per cleanup operation)
    Expected Result: confirm() calls found before cleanup bridge calls
    Failure Indicators: No confirm() calls, or confirm not before cleanup
    Evidence: .omo/evidence/task-6-confirm-dialogs.txt

  Scenario: Frontend build succeeds
    Tool: Bash
    Preconditions: SettingsModal.vue is saved
    Steps:
      1. Run: cd frontend && bun run build 2>&1 | tail -5
      2. Assert: Build succeeds
    Expected Result: Build completes with exit code 0
    Failure Indicators: TypeScript errors
    Evidence: .omo/evidence/task-6-build.txt
  ```

  **Commit**: YES (groups with 4)
  - Message: (shared with Task 4)
  - Files: `frontend/src/components/workspace/SettingsModal.vue`

- [ ] 7. Write backend test suite (12 test cases)

  **What to do**:
  - Create `tests/test_asr_gui_e2e.py` with 12 test cases covering all 8 audit issues:
    1. **Test 1**: Config defaults contain all engine-prefixed keys
    2. **Test 2**: Old generic `asr_compute_type` key is removed
    3. **Test 3**: Whisper default compute_type is `int8_float16`
    4. **Test 4**: Qwen default compute_type is `bfloat16`
    5. **Test 5**: qwen_transcribe.py uses bfloat16 (import and check source)
    6. **Test 6**: qwen_transcribe.py handles "auto" language
    7. **Test 7**: whisper_transcribe.py has vad_parameters support
    8. **Test 8**: whisper_transcribe.py handles "auto" language
    9. **Test 9**: main.py has only one cleanup_tasks_folder method
    10. **Test 10**: main.py reads engine-prefixed settings keys
    11. **Test 11**: main.py calls import_srt after transcription
    12. **Test 12**: Settings round-trip preserves engine-prefixed keys

  - Use `pytest` fixtures and parametrize where appropriate.
  - Tests should be runnable with `uv run pytest tests/test_asr_gui_e2e.py -v`.

  **Must NOT do**:
  - Do NOT import torch or run actual ASR models (these are config/source-level tests)
  - Do NOT require GPU or network access
  - Do NOT modify existing test files

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`python-testing`, `python-patterns`]
    - `python-testing`: pytest fixtures, parametrize, assertion patterns
    - `python-patterns`: Module introspection, AST patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 8)
  - **Blocks**: F1-F4 (final verification)
  - **Blocked By**: Tasks 1-5 (needs all implementations to exist)

  **References**:

  **Pattern References**:
  - `tests/` - Existing test directory. Check for conftest.py, test patterns.
  - `core/config.py` - After Task 1, contains engine-prefixed defaults. Test keys exist.
  - `core/asr_scripts/qwen_transcribe.py` - After Task 2, uses bfloat16. Test source inspection.
  - `core/asr_scripts/whisper_transcribe.py` - After Task 3, has vad_parameters. Test source inspection.
  - `main.py` - After Task 5, has SRT import + single cleanup. Test method counts.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: All 12 tests pass
    Tool: Bash
    Preconditions: All Wave 1-2 tasks complete
    Steps:
      1. Run: uv run pytest tests/test_asr_gui_e2e.py -v 2>&1
      2. Assert: Exit code 0, "12 passed" in output
    Expected Result: All 12 tests pass
    Failure Indicators: Any FAILED or ERROR
    Evidence: .omo/evidence/task-7-test-results.txt

  Scenario: Tests are fast (< 30 seconds total)
    Tool: Bash
    Preconditions: Tests exist
    Steps:
      1. Run: time uv run pytest tests/test_asr_gui_e2e.py -q 2>&1
      2. Assert: Total time < 30s
    Expected Result: Tests complete quickly (no model loading)
    Failure Indicators: Timeout or slow tests
    Evidence: .omo/evidence/task-7-test-speed.txt
  ```

  **Commit**: YES (standalone)
  - Message: `test(asr): add e2e test suite for 8 GUI issues`
  - Files: `tests/test_asr_gui_e2e.py`
  - Pre-commit: `uv run pytest tests/test_asr_gui_e2e.py -v`

- [ ] 8. Frontend TypeScript build verification

  **What to do**:
  - Run `cd frontend && bun run build` to verify all frontend changes compile cleanly.
  - If build fails, fix the TypeScript/Vue compilation errors.
  - Verify no `console.log` statements in production code (debug logs are acceptable in dev).
  - Verify no `@ts-ignore` or `as any` casts were introduced.

  **Must NOT do**:
  - Do NOT modify build configuration (vite.config.ts, tsconfig.json)
  - Do NOT add new dependencies
  - Do NOT change the output directory structure

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`frontend-patterns`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 7)
  - **Blocks**: F1-F4 (final verification)
  - **Blocked By**: Tasks 4, 6 (needs frontend changes to exist)

  **References**:

  **Pattern References**:
  - `frontend/tsconfig.json` - TypeScript configuration. Check strict mode settings.
  - `frontend/vite.config.ts` - Build configuration. Verify no custom plugins that might mask errors.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Frontend builds without errors
    Tool: Bash
    Preconditions: All frontend tasks (4, 6) complete
    Steps:
      1. Run: cd frontend && bun run build 2>&1
      2. Assert: Exit code 0, no "error" in output
    Expected Result: Build succeeds cleanly
    Failure Indicators: Non-zero exit code, TypeScript errors
    Evidence: .omo/evidence/task-8-build.txt

  Scenario: No @ts-ignore or as any in changed files
    Tool: Bash (grep)
    Preconditions: Build succeeds
    Steps:
      1. Run: grep -rn "@ts-ignore\|as any" frontend/src/pages/WorkspacePage.vue frontend/src/components/workspace/SettingsModal.vue | head -10
      2. Assert: No results (or only pre-existing ones)
    Expected Result: grep returns empty or only pre-existing entries
    Failure Indicators: New @ts-ignore or as any casts
    Evidence: .omo/evidence/task-8-type-safety.txt
  ```

  **Commit**: YES (groups with 4, 6)
  - Message: (shared with Task 4)
  - Files: `frontend/` (build output only)

---

## Final Verification Wave (MANDATORY -- after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** -- `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files exist in .omo/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** -- `unspecified-high`
  Run `cd frontend && bun run build` + `uv run pytest tests/test_asr_gui_e2e.py -v`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** -- `unspecified-high`
  Execute every QA scenario from every task. Save to `.omo/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** -- `deep`
  For each task: read "What to do", read actual diff (git diff). Verify 1:1. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Task 1+2+3**: `fix(asr): engine-prefixed settings defaults + dtype/compute_type fixes + vad_parameters` - core/config.py, core/asr_scripts/qwen_transcribe.py, core/asr_scripts/whisper_transcribe.py
- **Task 4+6**: `fix(asr): per-engine settings UI + device filtering + VAD sliders + confirm dialogs` - frontend/src/pages/WorkspacePage.vue, frontend/src/components/workspace/SettingsModal.vue
- **Task 5**: `fix(asr): SRT import after transcription + cleanup duplicate method + per-engine settings read` - main.py
- **Task 7**: `test(asr): add e2e test suite for 8 GUI issues` - tests/test_asr_gui_e2e.py
  Pre-commit: `uv run pytest tests/test_asr_gui_e2e.py -v`

---

## Success Criteria

### Verification Commands
```bash
uv run pytest tests/test_asr_gui_e2e.py -v    # Expected: 12 passed
cd frontend && bun run build                     # Expected: no errors
```

### Final Checklist
- [ ] All "Must Have" items present
- [ ] All "Must NOT Have" items absent
- [ ] All 12 test cases pass
- [ ] Frontend builds cleanly
- [ ] Settings persist across engine switches
- [ ] CPU plugins cannot select CUDA
- [ ] SRT generated and imported after transcription
- [ ] Auto-detect language works
