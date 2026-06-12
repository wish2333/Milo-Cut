# Milo-Cut v2.0.0 PRD

> Version: 2.0.0 (PRD Draft)
> Theme: Intelligence Evolution and Ecosystem
> Baseline: v1.3.0
> Date: 2026-06-11
> Role: Product Manager

---

## 0. Version Positioning

v2.0.0 is the intelligence evolution major release for Milo-Cut. Core goal: evolve from rule-driven to AI-driven, and upgrade Milo-Cut from a standalone tool to an embeddable, interoperable video preprocessing ecosystem component.

### Three Pillars

| Pillar | Code | Core Value |
|--------|------|----------|
| Intelligence Evolution | Pillar-A | Rule-based to LLM-driven semantic analysis |
| Ecosystem Interop | Pillar-B | Milo-Cut as plugin for ff-intelligent-neo |
| Product Delivery | Pillar-C | UIUX optimization, productized packaging |
---

## 1. Pillar-A: Intelligence Evolution

### 1.1 Current State (v1.3.0)

Current analysis_service.py is entirely rule-engine-based:

| Analysis | Implementation | Limitation |
|----------|---------------|------------|
| Filler Detection | String containment | Cannot recognize context-dependent fillers |
| Error Detection | Trigger word + lookahead | Manual trigger list, no semantic understanding |
| Duplicate Detection | n-gram cosine similarity | Semantically same but differently phrased reps undetectable |
| Punctuation Detection | Character set matching | ASR noise-sensitive, high false positive |

Core Problem: Rule engines cannot understand semantics.

### 1.2 LLM Topic Drift Detection

Perform paragraph-level topic analysis, detect off-topic sections, provide delete/keep suggestions.

User Scenario: User recorded 30-min tech talk, wants to auto-detect off-topic sections.

Process:
1. System segments transcript and sends to LLM (by paragraph or 30s window)
2. LLM returns topic label + relevance score (0-1) per segment
3. SuggestionPanel adds Topic Drift group with scores
4. Low-relevance segments default to Pending, high-relevance to Keep
5. User reviews and confirms/rejects

Functional Spec:
| Item | Spec |
|------|------|
| Input | Segment list + optional user topic description |
| Output | AnalysisResult(type=topic_drift) list |
| LLM Call | OpenAI-compatible API, streaming, token metering |
| Caching | Same project + transcript hash cached |
| Offline | Hide entry when LLM unavailable |

Data Model Extension (core/models.py):
- AnalysisResult type literal adds topic_drift, emotion
- New metadata: dict[str, Any] field for raw LLM response

Configuration (settings.json):
- llm.provider, llm.api_key, llm.base_url, llm.model
- llm.topic_drift_enabled, llm.topic_drift_sensitivity
- llm.emotion_analysis_enabled
- llm.max_tokens_per_request, llm.request_timeout_seconds
### 1.3 LLM Emotion Analysis

Analyze speaker emotional state (nervous, confident, flat, excited), label segments with emotion tags.

User Scenario:
1. System performs emotion analysis on transcript
2. Waveform view overlays emotion color bands (red=nervous, blue=confident, gray=flat)
3. SuggestionPanel adds Emotion Analysis group
4. User decides keep/delete based on emotion labels

Emotion Labels: calm, nervous, confident, excited, frustrated, neutral
Performance: Emotion + topic drift merged into single LLM call

### 1.4 LLM Smart Edit Suggestions

Generate a complete edit plan based on LLM understanding of transcript.

User Scenario: User imports 45-min video, LLM generates 30-min condensed edit plan.
Configuration: target duration, key content keywords, strategy (conservative/aggressive)
Output: list[EditDecision] with priority-sorted suggestions
Application: Batch write to project.edits as PENDING
New TaskType: LLM_SMART_EDIT

### 1.5 LLM Service Architecture

New core/llm_service.py as unified LLM entry point.

Key Design Constraints:
| Constraint | Description |
|-----------|-------------|
| Zero ML Dependencies | HTTP API only, no PyTorch/Transformers |
| Streaming Output | SSE streaming, real-time progress |
| Token Metering | Record tokens per call |
| Request Merging | Topic + emotion in single call |
| Cancel Support | Via TaskManager |
| Error Isolation | LLM unavailable不影响rule analysis |

### 1.6 Frontend Extensions

New Components:
- LlmSettingsPanel.vue (workspace/) - provider, key, model config
- TopicDriftPanel.vue (workspace/) - topic drift results
- EmotionTimeline.vue (waveform/) - emotion color bands
- SmartEditPanel.vue (workspace/) - smart edit plan + diff view

New Composables: useLlm.ts, useLlmAnalysis.ts, useSmartEdit.ts

New Events (core/events.py):
- llm:analysis_progress, llm:analysis_completed, llm:analysis_failed, llm:token_usage
---

## 2. Pillar-B: Ecosystem Interop

### 2.1 Current State

Two projects fully independent but share identical tech stack:

| Dimension | Milo-Cut | ff-intelligent-neo |
|-----------|-----------|-------------------|
| Framework | pywebview + Vue 3 + pywebvue | Same |
| Bridge | @expose + call() + _emit() | Same |
| Packaging | PyInstaller | Same |
| Python | 3.11 | Same |
| UI | Tailwind CSS 4 + DaisyUI 5 | Same |

Core Opportunity: pywebvue bridge layer already unified.

### 2.2 Interop Scenarios

Scenario A: Milo-Cut Edit -> Neo Export
- User completes edits in Milo-Cut
- MC sends edit timeline (JSON/EDL) to Neo
- Neo parses timeline, generates FFmpeg command
- User adjusts encoding params in Neo and exports
- Value: MC handles what to cut, Neo handles how to cut

Scenario B: Neo Batch -> Milo-Cut Analysis
- User adds videos to Neo task queue
- Neo sends video path list to MC
- MC batch creates projects, runs ASR + analysis
- MC returns edit suggestions per video
- Value: Neo as file entry point, MC as smart backend

### 2.3 Interop Protocol Design

Protocol Selection:
| Approach | Latency | Complexity | Use Case |
|----------|---------|-----------|----------|
| HTTP API (local) | Low | Medium | Neo calls MC analysis |
| File Protocol (JSON) | Medium | Low | Offline data exchange |
| WebSocket | Lowest | High | Reserved for v2.x |

v2.0.0 Recommended: File Protocol (primary) + HTTP API (optional)

File Protocol Spec:
- Protocol Name: milo-cut-protocol
- Format: JSON Lines (.milo.jsonl)
- Data Types:
  - edit_timeline (MC->Neo): segment times + edit actions
  - analysis_results (MC->Neo): analysis summary
  - export_request (Neo->MC): request project export
  - media_batch (Neo->MC): batch video paths for analysis
  - project_created (MC->Neo): creation confirmation
- Location: %APPDATA%/milo-cut/bridge/
- Monitoring: 500ms polling

HTTP API (optional, localhost:18230):
- GET /api/v1/health
- GET /api/v1/projects
- GET /api/v1/projects/{id}/timeline
- POST /api/v1/projects/{id}/export
- POST /api/v1/analyze
- GET /api/v1/analyze/{task_id}/status

Milo-Cut Bridge Service (core/bridge_service.py):
- File protocol dir management (publish/consume)
- HTTP server (optional)
- File polling for incoming Neo requests
- Health check for Neo availability

Neo Integration Points:
- Settings: Milo-Cut Integration section in Neo SettingsPage
- Send Button: TaskQueue context menu -> Send to Milo-Cut
- Receive Panel: Optional MC analysis results panel

### 2.4 Generic Plugin Interface

PluginInterface ABC for future DaVinci/Premiere integration.
Refactor existing export_timeline.py into pluginized architecture.
---

## 3. Pillar-C: UIUX and Product Delivery

### 3.1 UIUX Optimization

Current Issues:
| Issue | Severity | Description |
|-------|----------|-------------|
| Abrupt page transitions | Medium | v-if switch, no animation |
| Fixed workspace layout | Medium | No drag-to-resize |
| Low suggestion density | Medium | Flat list, no grouping |
| Missing step nav | High | design-spec.md controller not built |
| Incomplete shortcuts | Low | Missing Ctrl+S, Ctrl+G |
| No responsive design | Low | Overflow on small windows |

P0 Items:
- C-01: Global Step Navigation (5-step controller)
- C-02: Page Transition Animation (300ms fade-slide)
- C-03: Workspace Split Drag (30-70% range)

P1 Items:
- C-04: Suggestion Panel Refactor (card groups, priority sort)
- C-05: Keyboard Shortcut System
- C-06: Export Page Reorganization
- C-07: Empty State Design

P2 Items:
- C-08: Theme Color Customization
- C-09: Subtitle Font Size Adjustment
- C-10: Micro-interaction Animations

Design System Alignment:
- Step controller: implement per design-spec.md
- Subtitle row: add emotion/topic drift status colors
- Waveform: add emotion color band overlay
- Suggestion panel: refactor to complete card system
- Buttons: unify to pill shape

### 3.2 Productized Packaging

Current Issues:
| Issue | Description |
|-------|-------------|
| Windows only | macOS lacks .app packaging |
| No auto-update | Manual download |
| No splash screen | White screen on launch |
| Scattered version | 3 places to maintain |

P0 Improvements:
- D-01: macOS .app Packaging (reference Neo BUNDLE config)
- D-02: Splash Screen
- D-03: Single Version Source (pyproject.toml)

P1 Improvements:
- D-04: Windows NSIS Installer (optional)
- D-05: App Icon (.ico + .icns)
- D-06: Crash Reporting

Delivery Artifacts:
- Windows x64: .zip (onedir) + .exe (onefile)
- macOS: .app (BUNDLE) + .dmg
- Universal: portable (no install)
---

## 4. Scope and Priority

### 4.1 Feature Priority Matrix

| Feature | Prio | Pillar | Deps | Effort (pd) |
|---------|------|--------|------|-------------|
| LLM Service Architecture | P0 | A | None | 3 |
| Topic Drift (backend) | P0 | A | LLM Svc | 3 |
| Topic Drift (frontend) | P1 | A | backend | 3 |
| Emotion Analysis (backend) | P1 | A | LLM Svc | 2 |
| Emotion Analysis (frontend) | P1 | A | backend | 2 |
| Smart Edit (backend) | P1 | A | all above | 4 |
| Smart Edit (frontend) | P1 | A | backend | 4 |
| LLM Settings Panel | P0 | A | None | 2 |
| File Protocol Spec | P0 | B | None | 2 |
| Bridge Service | P1 | B | protocol | 3 |
| Neo Integration UI | P2 | B | bridge | 2 |
| HTTP API (optional) | P2 | B | bridge | 3 |
| Global Step Navigation | P0 | C | None | 3 |
| Split Drag | P1 | C | None | 2 |
| Page Transition | P1 | C | None | 1 |
| Suggestion Refactor | P1 | C | A | 3 |
| Keyboard Shortcuts | P2 | C | None | 2 |
| macOS Packaging | P1 | C | None | 2 |
| Splash Screen | P2 | C | None | 1 |
| Single Version Source | P0 | C | None | 0.5 |

Total estimated: ~51 person-days

### 4.2 Implementation Phases

Phase 1 (Jul 1-4): Foundation
- LLM Service Architecture, File Protocol Spec, Global Step Nav
- Single Version Source, LLM Settings Panel

Phase 2 (Jul 7-18): Core Features
- Topic Drift (backend+frontend), Emotion Analysis (backend+frontend)
- Smart Edit (backend+frontend), Bridge Service

Phase 3 (Jul 15-18): UIUX Polish
- Split Drag + Transitions, Suggestion Panel Refactor
- Keyboard Shortcuts

Phase 4 (Jul 21-25): Delivery
- macOS Packaging, Splash Screen, Neo Integration
- Integration Testing + Docs

### 4.3 MVP Cut Strategy

Must Include (v2.0.0 MVP):
- LLM Service + Topic Drift (backend+frontend) + LLM Settings
- File Protocol + Bridge Service framework
- Global Step Nav + Single Version Source

Defer to v2.1.0:
- Emotion Analysis (independent)
- Smart Edit Suggestions (depends on emotion)
- Neo Integration UI
- HTTP API
- Keyboard Shortcuts, Splash Screen
---

## 5. Technical Risks

| Risk | Impact | Prob | Mitigation |
|------|--------|------|------------|
| LLM API instability | Analysis unavailable | Med | Retry + backoff + degradation |
| High LLM latency | Poor UX | High | Streaming progress + cancel |
| Token costs | User API expense | Med | Estimation + confirmation dialog |
| Protocol divergence | Neo mismatch | Low | Doc first + shared types |
| macOS packaging | PyWebView diffs | Med | Reference Neo config |
| Bundle bloat | Larger download | Low | Code splitting + lazy load |

---

## 6. Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Analysis Coverage | 4 rules | 4 rules + 2 LLM |
| Topic Drift Accuracy | N/A | >= 70% adoption rate |
| Editing Efficiency | Manual | Smart edit + review |
| Cross-app Interop | None | File protocol + HTTP |
| Platform Support | Win only | Win + macOS |
| Startup Experience | White 2-3s | Splash + <1s |

---

## 7. Open Questions

| ID | Question | Suggestion |
|----|----------|------------|
| Q-01 | Which LLM providers? | OpenAI-compatible (GPT-4o-mini, DeepSeek, Qwen) |
| Q-02 | Local LLM? | Not v2.0.0, v2.x via Ollama |
| Q-03 | Neo interop priority? | File P0, HTTP P2, Neo UI P2 |
| Q-04 | User API keys? | Yes, MC does not host keys |
| Q-05 | Cloud sync? | Not v2.0.0, pure local |
| Q-06 | Audio-based emotion? | Text-only v2.0.0, v2.x combine audio |

---

## Appendix A: Architecture Comparison

Milo-Cut: main.py (MiloCutApi) -> project_service, analysis_service,
  export_service, ffmpeg_service, plugin_manager, task_manager

ff-intelligent-neo: main.py (FFmpegApi) -> command_builder,
  task_runner, auto_editor_api

Shared: pywebvue (Bridge + @expose), Vue 3 + TypeScript, Tailwind + DaisyUI

## Appendix B: Event Sync Matrix

| Milo-Cut Event | Neo Action |
|----------------|------------|
| project:saved | Pull timeline |
| analysis:updated | Pull analysis |
| llm:analysis_completed | Pull results |

## Appendix C: Data Model Changes

core/models.py:
- New: LlmProvider enum (openai, deepseek, qwen, custom)
- New: LlmConfig model (provider, api_key, base_url, model, etc.)
- AnalysisResult: add metadata field
- TaskType additions: LLM_SMART_EDIT, LLM_TOPIC_DRIFT, LLM_EMOTION

settings.json:
- llm section: provider, api_key, base_url, model, topic_drift_enabled, etc.
- bridge section: enabled, protocol_dir, http_port, http_enabled
