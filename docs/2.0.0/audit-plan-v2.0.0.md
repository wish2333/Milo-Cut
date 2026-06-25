# Milo-Cut v2.0.0 Execution Plan

> Version: 1.0
> Date: 2026-06-11
> Baseline: PRD-v2.0.0.md + audit-report-v2.0.0.md
> Scope: MVP features only, full scope见 PRD 4.3

---

## 0. Scope Confirmation

### MVP Inclusion (v2.0.0)

| Feature | Pillar | Effort (pd) |
|---------|--------|-------------|
| LLM Service Architecture | A | 3 |
| Topic Drift (backend) | A | 3 |
| Topic Drift (frontend) | A | 3 |
| LLM Settings Panel | A | 2 |
| File Protocol Spec | B | 2 |
| HTTP API (localhost) | B | 3 |
| Bridge Service | B | 3 |
| Global Step Navigation | C | 3 |
| Single Version Source | C | 0.5 |
| **MVP Total** | | **22.5 pd** |

### MVP Defer (v2.1.0+)

| Feature | Pillar | Reason |
|---------|--------|--------|
| Emotion Analysis (backend+frontend) | A | Independent, deferrable |
| Smart Edit (backend+frontend) | A | Depends on Topic Drift validation |
| Neo Integration UI | B | Depends on Bridge Service stabilization |
| Keyboard Shortcuts | C | Non-critical UX polish |
| Splash Screen | C | Non-critical UX polish |
| macOS .app Packaging | C | Platform expansion, non-blocking |

### Audit Fixes (from audit-report-v2.0.0.md)

| Fix | Effort (pd) | Source |
|-----|-------------|--------|
| LLM Chunking Strategy (backend) | 1 | B-03 |
| LLM Chunking Merge (frontend) | 0.5 | B-03 |
| HTTP API as Primary Protocol | 0 (absorbed in HTTP API task) | B-02 |
| Token Estimation Utility | 0.5 | M-02 |
| Emotion Confidence Schema | 0.5 | M-01 |
| Shortcut Focus Rules (doc only) | 0 | M-04 |
| **Audit Fix Total** | **2.5 pd** | |

### Grand Total: 25 pd

---

## 1. Phase Breakdown

### Phase 1: Foundation (Jul 1-4, 4 days)

> 目标：建立 LLM 服务层和 HTTP 通信基础

#### Task 1.1: LLM Service Architecture [3 pd]

**Deliverable:** `core/llm_service.py`

```
core/llm_service.py        # NEW - unified LLM entry point
core/models.py             # MODIFY - add LlmConfig, LlmProvider
core/events.py             # MODIFY - add llm:* events
data/settings.json         # MODIFY - add llm config section
```

Implementation:
- [ ] `LlmConfig` model (provider, api_key, base_url, model, max_tokens, timeout)
- [ ] `LlmProvider` enum (openai, deepseek, qwen, custom)
- [ ] `LlmService` class with `call(prompt, system, schema)` -> streaming response
- [ ] OpenAI-compatible HTTP client (using `httpx`, no OpenAI SDK)
- [ ] Retry + exponential backoff (max 3 retries)
- [ ] Token estimation: `estimate_tokens(text) -> int`
  - Chinese: `chars / 1.5`
  - English: `chars / 4.0`
  - Mixed: weighted by character type
- [ ] Cancel support via `threading.Event`
- [ ] Error isolation: LLM failure does not crash app
- [ ] Health check: `is_available() -> bool`

Events to add (`core/events.py`):
- `LLM_ANALYSIS_PROGRESS = "llm:analysis_progress"`
- `LLM_ANALYSIS_COMPLETED = "llm:analysis_completed"`
- `LLM_ANALYSIS_FAILED = "llm:analysis_failed"`
- `LLM_TOKEN_USAGE = "llm:token_usage"`

Bridge integration (`main.py`):
- [ ] `@expose test_llm_connection()` - validate API key + connectivity
- [ ] `@expose get_llm_config()` - read settings
- [ ] `@expose update_llm_config(config)` - write settings

Validation:
- [ ] Unit tests for `estimate_tokens()` (Chinese, English, mixed)
- [ ] Unit tests for `LlmConfig` serialization
- [ ] Manual test: connect to DeepSeek API, send prompt, receive response

#### Task 1.2: LLM Settings Panel [2 pd]

**Deliverable:** `frontend/src/components/workspace/LlmSettingsPanel.vue`

```
frontend/src/components/workspace/LlmSettingsPanel.vue   # NEW
frontend/src/composables/useLlm.ts                       # NEW
frontend/src/utils/events.ts                             # MODIFY
```

Implementation:
- [ ] Provider dropdown (OpenAI, DeepSeek, Qwen, Custom)
- [ ] Base URL field (auto-fill based on provider, editable for Custom)
- [ ] API Key field (password type, with show/hide toggle)
- [ ] Model name field (auto-fill defaults, editable)
- [ ] "Test Connection" button with status indicator
- [ ] Save/Cancel buttons
- [ ] UI text: "API Key is stored locally and never sent to our servers"
- [ ] `useLlm.ts` composable: `testConnection()`, `getConfig()`, `updateConfig()`
- [ ] Hidden feature: if Base URL = `http://localhost:11434/v1`, show "Ollama detected" badge

Events to add (`frontend/src/utils/events.ts`):
- Sync with `core/events.py` new entries

#### Task 1.3: HTTP API Foundation [2 pd]

**Deliverable:** `core/bridge_service.py` (HTTP portion)

```
core/bridge_service.py     # NEW - HTTP server + file protocol manager
core/models.py             # MODIFY - add BridgeConfig
```

Implementation:
- [ ] `BridgeService` class with optional HTTP server
- [ ] HTTP endpoints (localhost:18230):
  - `GET /api/v1/health` -> `{"status": "ok", "version": "2.0.0"}`
  - `GET /api/v1/projects` -> project list
  - `GET /api/v1/projects/{name}/timeline` -> segment times + edit actions
  - `POST /api/v1/analyze` -> trigger analysis (async, returns task_id)
  - `GET /api/v1/analyze/{task_id}/status` -> poll analysis status
- [ ] Thread-safe: HTTP server runs in background thread
- [ ] Graceful start/stop with app lifecycle
- [ ] CORS: `Access-Control-Allow-Origin: *` (safe: server bound to 127.0.0.1, no external access)
  - Note: strict localhost-only CORS blocks pywebview custom protocol origins (pywebview://) and cross-app requests from Neo's frontend
- [ ] Config: `bridge.http_enabled`, `bridge.http_port` in settings.json

Bridge integration (`main.py`):
- [ ] Start `BridgeService` on app init
- [ ] Stop on app destroy
- [ ] `@expose get_bridge_status()` -> HTTP server running + port

Validation:
- [ ] Unit test: health endpoint returns correct version
- [ ] Unit test: projects endpoint returns project list
- [ ] Manual test: curl endpoints while app is running

#### Task 1.4: Single Version Source [0.5 pd]

**Deliverable:** Version managed in `pyproject.toml` only

```
pyproject.toml             # MODIFY - single version source
core/__init__.py           # MODIFY - read from pyproject.toml
main.py                    # MODIFY - read from core.__init__
build.py                   # MODIFY - read from pyproject.toml
frontend/package.json      # MODIFY - read from pyproject.toml (build time)
```

Implementation:
- [ ] `pyproject.toml` is the single version source
- [ ] `core/__init__.py` reads version via `importlib.metadata`
- [ ] `build.py` reads from `pyproject.toml`
- [ ] `frontend/package.json` version synced at build time (bun script)
- [ ] Remove any hardcoded version strings elsewhere

---

### Phase 2: Core Features (Jul 7-15, 7 days)

> 目标：Topic Drift 完整实现 + Bridge Service 通信协议

#### Task 2.1: Topic Drift Backend [3 pd]

**Deliverable:** Topic drift analysis in `core/llm_service.py`

```
core/llm_service.py        # MODIFY - add topic drift analysis
core/models.py             # MODIFY - add topic_drift to AnalysisResult type
core/task_manager.py       # MODIFY - add LLM_TOPIC_DRIFT TaskType
```

Implementation:
- [ ] `TaskType.LLM_TOPIC_DRIFT` enum value
- [ ] Chunking logic in `LlmService`:
  - `chunk_transcript(segments, chunk_duration=300, overlap=30) -> list[Chunk]`
  - Each chunk: 5 min of segments with 30s overlap
  - Token budget check: skip chunks exceeding `max_segment_tokens`
- [ ] Topic drift prompt template:
  - System: "Analyze video transcript segments for topic relevance"
  - User: segments text + optional topic description
  - Output schema: `list[{segment_id, topic, relevance: 0-1}]`
- [ ] Streaming: process chunks sequentially, emit `llm:analysis_progress` per chunk
- [ ] Result emitting: send per-chunk results immediately via event (no wait-for-all)
  - Each chunk result includes `segment_id` for frontend upsert
- [ ] Caching: key = `project_id + transcript_hash`, store in project data
- [ ] Fallback: if LLM unavailable, hide Topic Drift entry entirely
- [ ] Token metering: emit `llm:token_usage` event per request

Bridge integration (`main.py`):
- [ ] `@expose start_topic_drift(project_name, topic_description?)` -> task_id
- [ ] `@expose get_topic_drift_results(project_name)` -> cached results

Validation:
- [ ] Unit test: chunk_transcript produces correct 5-min chunks
- [ ] Unit test: overlap deduplication logic
- [ ] Unit test: token estimation within 20% of actual
- [ ] Integration test: full topic drift flow with mock LLM

#### Task 2.2: Topic Drift Frontend [3 pd]

**Deliverable:** `TopicDriftPanel.vue` + integration

```
frontend/src/components/workspace/TopicDriftPanel.vue   # NEW
frontend/src/composables/useLlmAnalysis.ts              # NEW
frontend/src/composables/useTopicDrift.ts               # NEW
```

Implementation:
- [ ] `TopicDriftPanel.vue`:
  - Topic description input (optional)
  - "Analyze" button (disabled when LLM not configured)
  - Progress bar (streaming per-chunk)
  - Result list: segment_id based upsert (update if exists, append if new)
    - Overlap region dedup handled naturally: same segment_id from adjacent chunks overwrites with latest relevance
    - No flicker or duplicate entries in UI
  - Each result: segment text preview + topic label + relevance badge
  - Color coding: relevance >= 0.7 green (keep), < 0.4 red (delete), else yellow (pending)
  - Batch actions: "Accept all suggestions" / "Reject all"
- [ ] `useLlmAnalysis.ts` composable:
  - Shared analysis lifecycle: start, progress, complete, fail
  - Token usage display
- [ ] `useTopicDrift.ts` composable:
  - `startAnalysis(projectName, topicDescription?)`
  - Reactive results + loading state
- [ ] Integration into WorkspacePage:
  - Topic Drift tab in SuggestionPanel
  - Offline indicator when LLM not configured

#### Task 2.3: Bridge Service - File Protocol [1 pd]

**Deliverable:** File protocol in `core/bridge_service.py`

```
core/bridge_service.py     # MODIFY - add file protocol
```

Implementation:
- [ ] File protocol dir management:
  - Publish dir: `%APPDATA%/milo-cut/bridge/outgoing/`
  - Consume dir: `%APPDATA%/milo-cut/bridge/incoming/`
- [ ] Write `.milo.jsonl` files for outgoing data:
  - `edit_timeline`: segment times + edit actions
  - `analysis_results`: analysis summary
- [ ] Read `.milo.jsonl` from incoming dir (polling, 2s interval, not 500ms)
- [ ] File rotation: processed files moved to `archive/` subdirectory
- [ ] File locking: write to temp file, then atomic rename
  - Use `os.replace()` (NOT `os.rename()`) -- on Windows, `os.rename()` raises FileExistsError if target exists; `os.replace()` overwrites atomically

---

### Phase 3: UIUX Polish (Jul 16-18, 3 days)

> 目标：全局步骤导航 + 工作区分栏拖拽 + 页面过渡动画

#### Task 3.1: Global Step Navigation [3 pd]

**Deliverable:** 5-step controller per design-spec.md

```
frontend/src/components/common/StepController.vue       # NEW
frontend/src/App.vue                                     # MODIFY
frontend/src/composables/useStepNav.ts                   # NEW
```

Implementation:
- [ ] `StepController.vue` per design-spec.md:
  - 5 steps: Import -> Analyze -> Edit -> Review -> Export
  - Current step highlighted, completed steps checkmarked
  - Clickable for navigation (forward only, or to any completed step)
  - Responsive: horizontal on desktop, compact on narrow windows
- [ ] `useStepNav.ts` composable:
  - Reactive `currentStep` state
  - `goToStep(n)`, `nextStep()`, `prevStep()`
  - Step validation: cannot skip unfinished steps
- [ ] `App.vue` integration:
  - Use dynamic component `<component :is="currentPageComponent">` + `<Transition>`
  - Do NOT introduce vue-router -- current v-if / dynamic component pattern is sufficient and avoids 3 pd schedule overrun
  - Each step maps to existing page components
  - Step state persisted per project

#### Task 3.2: Workspace Split Drag [1 pd]

**Deliverable:** Resizable split panel in WorkspacePage

```
frontend/src/components/common/SplitPanel.vue            # NEW
frontend/src/components/WorkspacePage.vue                # MODIFY
```

Implementation:
- [ ] `SplitPanel.vue`:
  - Horizontal split with draggable divider
  - Range constraint: 30%-70% (left panel)
  - Persist split ratio in localStorage
  - Smooth drag with CSS `cursor: col-resize`
- [ ] `WorkspacePage.vue`:
  - Replace fixed layout with SplitPanel
  - Left: SubtitleList / Timeline
  - Right: SuggestionPanel / WaveformView

#### Task 3.3: Page Transition Animation [0.5 pd]

**Deliverable:** Smooth page transitions in App.vue

Implementation:
- [ ] Replace `v-if` with Vue `<Transition>` component
- [ ] 300ms fade-slide animation (CSS)
- [ ] Forward: slide-left + fade-in
- [ ] Backward: slide-right + fade-in
- [ ] Respect `prefers-reduced-motion` media query

---

### Phase 4: Integration & Delivery (Jul 21-25, 5 days)

> 目标：集成测试、文档更新、发布准备

#### Task 4.1: Integration Testing [2 pd]

- [ ] LLM full flow: settings -> topic drift -> results display -> edit apply
- [ ] Bridge Service: HTTP API endpoints with external curl/Postman
- [ ] Bridge Service: File Protocol write + read + archive cycle
- [ ] Step Navigation: all 5 steps forward/backward with data preservation
- [ ] Split Panel: drag + persist + responsive
- [ ] LLM offline: verify graceful degradation (hide AI features)
- [ ] Token estimation: compare estimated vs actual for 3+ video lengths
- [ ] Error scenarios: invalid API key, network timeout, malformed response

#### Task 4.2: Event Sync Verification [1 pd]

- [ ] Verify `core/events.py` and `frontend/src/utils/events.ts` are in sync
- [ ] New events: all 4 LLM events registered in both files
- [ ] No orphaned events (defined in one file but not the other)
- [ ] Optional build-time safeguard: add grep check to `frontend/package.json` build script
  - Verify all `llm:*` strings in `.ts` files exist in `core/events.py`
  - Prevents cross-language typos from reaching production

#### Task 4.3: Documentation Update [1 pd]

- [ ] Update `docs/backend-guide.md` with LLM service architecture
- [ ] Update `docs/frontend-guide.md` with new components and composables
- [ ] Update `CLAUDE.md` with v2.0.0 architecture changes
- [ ] Update `tests/TEST_GUIDE.md` with new test scenarios
- [ ] Update `docs/design-spec.md` step controller implementation notes

#### Task 4.4: Release Preparation [1 pd]

- [ ] Version bump in `pyproject.toml` to `2.0.0`
- [ ] Verify frontend build: `cd frontend && bun run build`
- [ ] Verify backend tests: `uv run pytest`
- [ ] Windows build test: `uv run build.py --onedir`
- [ ] Release notes draft
- [ ] Git tag `v2.0.0`

---

## 2. Dependency Graph

```
Phase 1 (Foundation)
  1.1 LLM Service ─────────┐
  1.2 LLM Settings Panel ──┤ (parallel, 1.1 provides backend)
  1.3 HTTP API Foundation ─┤ (independent)
  1.4 Single Version ──────┘ (independent)
                            │
                            v
Phase 2 (Core Features)
  2.1 Topic Drift Backend ──┐ (depends on 1.1)
  2.2 Topic Drift Frontend ─┤ (depends on 2.1 + 1.2)
  2.3 File Protocol ────────┘ (depends on 1.3)
                            │
                            v
Phase 3 (UIUX Polish)
  3.1 Step Navigation ──┐ (independent)
  3.2 Split Drag ───────┤ (independent)
  3.3 Transitions ──────┘ (depends on 3.1)
        │
        v
Phase 4 (Integration)
  4.1 Integration Tests ──┐ (depends on all above)
  4.2 Event Sync ─────────┤ (depends on all above)
  4.3 Documentation ──────┤ (depends on all above)
  4.4 Release Prep ────────┘ (depends on 4.1-4.3)
```

---

## 3. Risk Mitigation Schedule

| Risk | Mitigation | When |
|------|-----------|------|
| LLM API instability | Retry + backoff + offline fallback | Phase 1 (Task 1.1) |
| LLM output truncation | Chunking strategy (5-min chunks, 30s overlap) | Phase 2 (Task 2.1) |
| File Protocol lock conflicts | HTTP API as primary, file polling at 2s (not 500ms) | Phase 1 (Task 1.3) |
| High LLM latency | Streaming progress per chunk, cancel support | Phase 2 (Task 2.1) |
| Token costs | Estimation dialog before analysis starts | Phase 2 (Task 2.2) |
| Protocol divergence with Neo | Documented protocol spec before implementation | Phase 1 (Task 1.3) |

---

## 4. Acceptance Criteria

### MVP Release Criteria

- [ ] LLM connectivity: user can configure provider + key + model, test connection succeeds
- [ ] Topic Drift: 10-min video analysis completes with visible results
- [ ] Topic Drift: 30-min+ video handled via chunking without truncation
- [ ] Topic Drift: results display with relevance scores, batch accept/reject works
- [ ] LLM offline: AI features hidden gracefully, rule-based analysis unaffected
- [ ] HTTP API: all 5 endpoints respond correctly via curl
- [ ] File Protocol: write + read + archive cycle works
- [ ] Step Navigation: 5 steps navigable with state preservation
- [ ] Split Panel: draggable between 30-70%, persists across sessions
- [ ] No regression: existing features (silence detection, export, waveform) unaffected
- [ ] Frontend build: `bun run build` passes with zero errors
- [ ] Backend tests: `uv run pytest` passes with >= 80% coverage on new code

### Quality Gates Per Phase

| Phase | Gate |
|-------|------|
| Phase 1 complete | LLM connection test passes, HTTP health endpoint responds, version reads from pyproject.toml |
| Phase 2 complete | Topic drift analysis produces results for test video, bridge endpoints functional |
| Phase 3 complete | Step controller navigates all 5 steps, split panel drags smoothly |
| Phase 4 complete | All acceptance criteria above pass |

---

## 5. Schedule Overview

```
Jul 2026
Week 1: [1][2][3][4]  Phase 1: Foundation
Week 2: [7][8][9][10][11]  Phase 2: Core Features (5 days)
Week 3: [14][15][16][17][18]  Phase 2 cont (2d) + Phase 3: UIUX (3d)
Week 4: [21][22][23][24][25]  Phase 4: Integration & Delivery

        Phase 1    Phase 2         Phase 3    Phase 4
Week 1  |########|
Week 2           |##############|
Week 3                          |########|
Week 4                                   |##########|
```

Total: 25 pd across 19 working days
Team assumption: 1.3 developers (primary + part-time support)
