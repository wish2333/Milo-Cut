# Milo-Cut v2.0.0 PRD Audit Report

> Version: 1.0
> Date: 2026-06-11
> Scope: PRD-v2.0.0.md full review
> Dimensions: Technical Feasibility, UX, Architecture, Project Management

---

## 0. Executive Summary

PRD v2.0.0 is a well-structured document with clear pillar separation and realistic scoping. The audit identified **3 high-priority blockers**, **4 medium-priority improvements**, and **6 low-priority suggestions**. All Open Questions received actionable recommendations.

**Overall Assessment: PRD quality is HIGH. After resolving the 2 blockers below, development can proceed.**

---

## 1. High-Priority Risks (Blockers)

### ~~B-01: macOS Code Signing and Notarization~~ -- RESOLVED

| Item | Detail |
|------|--------|
| Pillar | C (Product Delivery) |
| PRD Ref | Section 3.2, D-01 |
| Severity | ~~Blocker~~ -> Non-Issue |
| Status | RESOLVED (mentor feedback) |

**Original Concern:**
macOS Gatekeeper blocks unsigned `.app` bundles.

**Resolution:**
Mentor decision: professional packaging (code signing, notarization, NSIS installer) will NOT be pursued in this project. Current packaging mechanism is sufficient:

- **Windows**: Portable zip (onedir) + single exe (onefile), no installation required
- **macOS**: `.app` BUNDLE, users can bypass Gatekeeper via right-click "Open"

This is a pragmatic decision for an open-source desktop tool -- the $99/year Apple Developer certificate and CI/CD signing complexity are not justified for the current user base.

**PRD Impact:** No changes needed. D-01 remains as-is (macOS `.app` packaging, P1, 2 pd).

---

### B-02: File Polling IPC Poses Windows Compatibility Risk

| Item | Detail |
|------|--------|
| Pillar | B (Ecosystem Interop) |
| PRD Ref | Section 2.3, File Protocol Spec |
| Severity | **Blocker** |
| Status | MISALIGNED PRIORITY |

**Problem:**
500ms file system polling on Windows causes:
1. **File lock conflicts** -- Neo writing `.milo.jsonl` while Milo-Cut reads triggers `SharingViolation` errors
2. **I/O performance degradation** -- sustained polling on HDD (common in target user hardware) causes noticeable slowdown
3. **Antivirus interference** -- rapid file creation/modification triggers real-time scanning in Defender and third-party AV

**Impact:**
- Protocol reliability issues in production
- Difficult to debug (intermittent failures)
- Negative first impression for cross-app interop

**Recommendation:**
1. **Reverse protocol priority** in PRD Section 2.3:
   - HTTP API (localhost:18230) -> P0 (primary)
   - File Protocol (.milo.jsonl) -> P1 (offline fallback, large data exchange)
   - WebSocket -> P2 (reserved for v2.x)

2. HTTP API advantages over File Polling:

| Dimension | File Polling (500ms) | HTTP API (localhost) |
|-----------|---------------------|---------------------|
| Latency | ~250ms average | <5ms |
| Windows file locks | High risk | None |
| AV interference | Medium risk | None |
| Debugging | Hard (parse JSONL) | Easy (curl / browser) |
| Error handling | Partial (missing file) | Standard HTTP codes |
| Bidirectional | Requires dual dirs | Request-response |

3. Update Phase allocation:
   - Phase 1: Add HTTP API foundation (3 pd, from freed Smart Edit budget)
   - Phase 2: Bridge Service builds on HTTP API
   - File Protocol deferred to Phase 4

**Effort Impact:** +3 pd in Phase 1, offset by Smart Edit deferral (-8 pd in Phase 2)

---

### B-03: LLM Output Length Limits for Long Videos

| Item | Detail |
|------|--------|
| Pillar | A (Intelligence Evolution) |
| PRD Ref | Section 1.4, Smart Edit |
| Severity | **Blocker** |
| Status | NOT ADDRESSED |

**Problem:**
A 45-minute presentation transcript contains ~15,000-20,000 Chinese characters (~10,000-13,000 tokens). Asking LLM to:
1. Ingest full transcript as input context
2. Output hundreds of EditDecision objects with timestamps

This will hit model `max_tokens` output limits (typically 4,096-16,384), causing JSON truncation and parse failures.

**Impact:**
- Smart Edit fails silently on videos >10 minutes
- JSON truncation produces invalid partial results
- Users lose trust in AI suggestions

**Recommendation:**
1. Add **Chunking Strategy** sub-section to PRD Section 1.5:

```
Chunking Parameters:
- chunk_duration: 5 minutes (configurable)
- chunk_overlap: 30 seconds (prevents boundary loss)
- max_chunks_per_request: 1-3 (dynamically adjusted by model max_tokens)
- estimated_tokens_per_chunk: ~2000 (Chinese), ~800 (English)

Smart Edit Flow:
1. Segment transcript into 5-min chunks with 30s overlap
2. Send 1-3 chunks per LLM request (based on model capacity)
3. Each request returns partial EditDecision list
4. Frontend merges results by timestamp, deduplicates overlap region
5. Present merged plan to user for review
```

2. Add to LLM Service Architecture constraints:
   - `max_segment_tokens` config field in settings.json
   - Token estimation function (local, no external deps)
   - Streaming merge logic in frontend useSmartEdit.ts

3. Add to Technical Risks table:
   - Risk: "LLM output truncation on long videos"
   - Impact: High
   - Probability: High
   - Mitigation: Chunking + streaming merge

**Effort Impact:** +1 pd for chunking logic (backend) + 0.5 pd (frontend merge)

---

## 2. Medium-Priority Improvements

### M-01: Emotion Label Confidence Display

| Pillar | PRD Ref | Severity |
|--------|---------|----------|
| A | Section 1.3 | Medium |

**Issue:** Text-only emotion analysis has limited accuracy for sarcasm, irony, and cultural speech patterns.

**Recommendation:**
- Backend `AnalysisResult` metadata includes `confidence: float` (0.0-1.0)
- Frontend EmotionTimeline renders low-confidence labels with `opacity: 0.4` + dashed border
- Tooltip text: "Based on text semantic analysis (confidence: 62%)"
- Threshold configurable: `llm.emotion_confidence_threshold` (default: 0.6)

---

### M-02: Token Cost Estimation Without tiktoken

| Pillar | PRD Ref | Severity |
|--------|---------|----------|
| A | Section 1.5 | Medium |

**Issue:** Zero ML Dependencies constraint prevents using `tiktoken` library for accurate token counting.

**Recommendation:**
- Implement local estimation formula:
  ```
  Chinese text: tokens = chars / 1.5
  English text: tokens = chars / 4.0
  Mixed content: weighted by character type ratio
  ```
- Display in confirmation dialog: "Estimated cost: ~$0.05 (approximation, actual may vary)"
- Backend utility in `core/llm_service.py`: `estimate_tokens(text: str) -> int`

---

### M-03: Cross-App Workflow Deep Link

| Pillar | PRD Ref | Severity |
|--------|---------|----------|
| B | Section 2.2, Scenario A | Medium |

**Issue:** Users switching between two independent windows creates fragmented experience.

**Recommendation:**
- Add "Render in Neo" button on Milo-Cut Export page
- Trigger custom URL scheme: `ff-intelligent-neo://import?source=milo-cut&format=edl&path=<file_path>`
- Neo registers URL scheme handler during installation
- Fallback: if Neo not running, show toast "Please launch ff-intelligent-neo first"

---

### M-04: Keyboard Shortcut Focus Rules

| Pillar | PRD Ref | Severity |
|--------|---------|----------|
| C | Section 3.1, C-05 | Medium |

**Issue:** Desktop apps using web tech (PyWebView + Vue) commonly suffer from global shortcuts firing inside text inputs.

**Recommendation:**
Add to PRD Section 3.1, C-05:
```
Shortcut Suppression Rules:
1. When focus is in input/textarea/contenteditable:
   - Suppress ALL global shortcuts
   - Preserve only browser defaults (Ctrl+A/C/V/X/Z)
2. When focus is on video player:
   - Only Space (play/pause) and arrow keys (seek) active
3. Global shortcuts require explicit registration
   - Use event.code matching, not event.key
   - Check document.activeElement before dispatching
```

---

## 3. Low-Priority Suggestions

### L-01: Suggestion Panel Visual Hierarchy

| Pillar | PRD Ref |
|--------|---------|
| C | Section 3.1, C-04 |

Consider adding severity-based color coding (from design-spec.md):
- Delete suggestions: red-tinted card
- Keep suggestions: green-tinted card
- Uncertain: gray/default card
- Sorted by confidence within each group

### L-02: Splash Screen Progress Indicator

| Pillar | PRD Ref |
|--------|---------|
| C | Section 3.2, D-02 |

Splash screen should show loading stages:
1. "Loading engine..." (FFmpeg probe)
2. "Preparing interface..." (Vue mount)
3. "Ready" (auto-dismiss)

### L-03: Error Isolation Documentation

| Pillar | PRD Ref |
|--------|---------|
| A | Section 1.5 |

Clarify that LLM unavailability should:
- Hide all AI-powered UI elements gracefully
- Fall back to existing rule-based analysis
- Show subtle status indicator: "AI features offline"

---

## 4. Open Questions Decisions

Based on PRD constraints and technical feasibility:

| ID | Decision | Rationale |
|----|----------|-----------|
| Q-01 | **OpenAI-compatible format only** | Maximum provider coverage with single integration. Default recommendation: DeepSeek (best cost/performance for Chinese text) or GPT-4o-mini |
| Q-02 | **Support in v2.0.0 as hidden feature** | Zero development cost -- OpenAI-compatible interface naturally supports Ollama (`http://localhost:11434/v1`). Document in advanced settings tooltip only |
| Q-03 | **REVERSE priority** | HTTP API P0 (reliable, debuggable), File Protocol P1 (offline fallback), Neo UI P2. See B-02 for detailed analysis |
| Q-04 | **Local-only storage** | Store in settings.json. UI must display "API key is stored locally and never sent to our servers" |
| Q-05 | **No cloud sync** | Correct decision. Desktop tool's competitive advantage is local privacy |
| Q-06 | **Text-only for v2.0.0** | Correct decision. Audio-based emotion requires local VAD/sentiment model, violates Zero ML Dependencies constraint. Defer to v2.x |

---

## 5. Scope and Schedule Impact Analysis

### Current Estimate (from PRD)

- Total: 51 person-days (pd)
- Timeline: Jul 1 - Jul 25 (18 working days)
- Implied team: ~2.8 developers

### MVP Scope (per PRD Section 4.3)

After deferring Smart Edit (8 pd) and Emotion Analysis (4 pd):
- MVP effort: ~39 pd
- 2 developers: ~20 working days (4 weeks) -- feasible
- 1 developer: ~39 working days (8 weeks) -- extends to mid-August

### Audit Impact on Estimates

| Change | Effort Delta | Notes |
|--------|-------------|-------|
| ~~macOS signing/notarization~~ | ~~+1.5 pd~~ | Resolved: not pursuing professional packaging |
| HTTP API upgrade to P0 (B-02) | +3 pd | Offset by Smart Edit deferral |
| LLM chunking strategy (B-03) | +1.5 pd | Backend + frontend |
| Deep Link integration (M-03) | +0.5 pd | Minimal implementation |
| **Net change** | **+5 pd** | |

### Revised MVP Estimate

- Revised MVP: ~44 pd
- 2 developers: ~22 working days (4.4 weeks)
- Recommended timeline adjustment: Jul 1 - Jul 28 (if 2-person team)

### Freed Budget Reallocation

Smart Edit deferral releases 8 pd. Recommended reallocation:

| Target | Priority | Effort |
|--------|----------|--------|
| HTTP API (B-02 fix) | P0 | 3 pd |
| LLM chunking (B-03 fix) | P0 | 1.5 pd |
| Integration test buffer | P0 | 2 pd |
| UI polish buffer | P1 | 1.5 pd |
| **Total** | | **8 pd** |

---

## 6. Technical Risks Additions

Append to PRD Section 5:

| Risk | Impact | Prob | Mitigation |
|------|--------|------|------------|
| Windows file lock conflicts in File Protocol | High | Med | HTTP API as primary protocol |
| LLM output truncation on long videos | High | High | Chunking + streaming merge |
| Text-only emotion analysis low accuracy | Med | High | Confidence display + user disclaimer |
| Token estimation inaccuracy | Low | Med | Conservative over-estimate + "approximate" label |

---

## 7. Summary of Required PRD Updates

When PRD is revised, these sections need changes:

| Section | Change Type | Description |
|---------|------------|-------------|
| 1.4 Smart Edit | Add | Chunking strategy sub-section |
| 1.5 LLM Architecture | Add | Chunking constraints, token estimation |
| 2.3 Protocol Design | Modify | HTTP API -> P0 primary, File Protocol -> P1 |
| 3.1 C-05 Shortcuts | Add | Focus suppression rules |
| 4.1 Priority Matrix | Modify | Update priorities per B-02/B-03 |
| 4.2 Phases | Modify | HTTP API moves to Phase 1 |
| 5. Technical Risks | Add | 4 new risk entries from Section 6 above |
| 7. Open Questions | Resolve | All 6 questions decided (see Section 4) |

---

## Appendix: Review Methodology

- Static analysis of PRD document structure and content
- Cross-reference with current codebase architecture (CLAUDE.md)
- Comparison with industry practices for desktop app distribution
- Platform-specific risk assessment (Windows 11, macOS)
- LLM integration best practices for production applications
