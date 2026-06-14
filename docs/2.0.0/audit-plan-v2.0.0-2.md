# Milo-Cut v2.0.0 Phase 4 实施计划

> Version: 1.0
> Date: 2026-06-14
> Scope: Phase 4 (LLM 功能重构 + 多 Timeline 基础设施 + 工程化前置 + 集成发布)
> Based on: `audit-report-v2.0.0-2.md` (实施问题审计), `audit-report-v2.0.0.md` (PRD 级审计), 外部审计反馈
> Status: **待批准**

---

## 0. 文档定位

本计划是 Phase 4 的**纲领性实施文件**，基于以下输入:

| 输入文档 | 作用 |
|----------|------|
| `audit-report-v2.0.0-2.md` | 识别 C-01/C-02 产品定位 + 设计缺陷，M-01/M-02/M-03 实施问题，L-01/L-02/L-03 工程改进 |
| `audit-report-v2.0.0.md` | PRD 级审计 (B-03 输出长度限制等) |
| 外部审计反馈 | 确认方向 E，补充工程化前置要求、时间戳断言层、并发/成本技术调研维度 |

**前置决策 (已确认):**

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 工程化前置 | Phase 4a 先完成 L-01/L-02/L-03 | 大规模重构前需测试套件稳定，避免雪崩 |
| 新增审计项 (成本/并发) | 仅技术调研，不纳入 v2.0.0 工期 | 当前无实现，v2.0.0 聚焦核心功能交付 |
| P1 时间戳断言 | 双层: dev raise / prod warn | 开发期强保证发现问题，生产期容错不中断 |

---

## 1. 当前基线快照

> 基于 `audit-report-v2.0.0-2.md` Appendix B，此处仅列关键数据点。完整对照见原附录。

### 1.1 已解决项 (无需 Phase 4 处理)

| ID | 状态 | 证据 |
|----|------|------|
| M-01 Bridge 回调绑定 | RESOLVED | `core/bridge_service.py:240-246` 用 `staticmethod()` 包装 |
| M-02 Timeline.vue import | RESOLVED | `frontend/src/components/workspace/Timeline.vue:1-8` 全部 `@/` 别名 |
| M-03 mock 字段 + expose | RESOLVED | `main.py:1042` `add_analysis_results` 已 `@expose`，`useSegmentEdit.test.ts:34` 已补 `topic_drift` |

### 1.2 待实施项 (Phase 4 范围)

| ID / 功能 | 当前状态 | 关键证据 |
|-----------|----------|----------|
| C-01 Topic Drift | 完整存在，待重构 | `core/llm_service.py:289-493`, `TopicDriftPanel.vue:1-187` |
| C-02 LLM 格式不对称 | OPEN | `core/llm_service.py:317-393` 仍 `str.format()` + regex |
| 多 Timeline 基础设施 | 未实施 | `core/models.py:280-287` 单扁平 `Project`，无 `Timeline` 模型 |
| P0 智能删除增强 | 未实施 | 0 匹配 |
| P1 字幕修正 | 未实施 | 0 匹配 |
| P2 亮点提取 | 未实施 | 0 匹配 |
| P3 语义搜索 | 未实施 | 0 匹配 |
| L-01 ESLint | 未实施 | 项目无 ESLint 配置/依赖 |
| L-02 mock 集中管理 | 未实施 | `tests/conftest.py` 仅 fixtures，无 mock 工厂 |
| L-03 API 同步检查 | 未实施 | `package.json:8` 仅 `sync-version` 同步版本号 |

### 1.3 关键技术约束 (影响实施)

| 约束 | 当前状态 | 影响 |
|------|----------|------|
| `TaskManager` 并发模型 | 已支持: `Semaphore(1)` 重任务 + `Semaphore(3)` 轻任务 + `PriorityQueue` (`core/task_manager.py:42-52`) | 多 Timeline 并发 LLM 任务有底层支撑，需验证状态隔离 |
| `ProjectService` 耦合 | ~49 处直接引用 `self._current.{transcript,edits,analysis}` (`core/project_service.py`) | 多 Timeline 重构需引入 `active_timeline` 属性统一替换，机械但范围大 |
| `chunk_transcript` | 时间分块: 5min chunk + 30s overlap (`core/llm_service.py:239-282`)，**非 token 分块** | P0 短窗口分析 (15-30s) 需新增分块策略 |
| Token 估算 | `estimate_tokens` 启发式 (CJK ~1.5 tok/char) (`core/llm_service.py:32-48`)，`call_llm` 已捕获 `usage` | 有基础，Cost Estimator 可基于此扩展 (技术调研) |
| `Segment.dirty_flags` | 已存在且在用: `text_edited` / `merged` / `split` / `search_replaced` (`core/models.py:70-79`) | P1 字幕修正可新增 `llm_corrected` flag，现有机制兼容 |
| 前端 `tsconfig.json` | 已 `"strict": true` + `noUnusedLocals/Parameters` (`frontend/tsconfig.json:14-17`) | 前端类型安全已有，无需额外加严 |
| Python lint | `pyproject.toml` 无 `[tool.ruff]`，无任何 linter | L-01 Python 侧需从零引入 ruff |
| 测试套件 | 15 文件 ~135 测试，无 `@pytest.mark.integration`，无 TaskManager 集成测试 | L-02 mock 抽离后需补充集成测试 |

---

## 2. Phase 4 总体路线图

```
Phase 4a: 工程化前置 + 多 Timeline 基础设施
  ├── L-01: ruff (Python) + ESLint (前端) 引入
  ├── L-02: 测试 mock 工厂抽离 (前后端)
  ├── L-03: API 同步检查脚本
  └── 多 Timeline: Timeline 模型 + ProjectService 重构 + 迁移 + UI 切换器
         │
Phase 4b: P0 智能删除增强 + P1 字幕修正
  ├── C-02 解决: LLM 输入结构化 + 输出分层降级
  ├── P0: 短窗口 LLM 补盲区 -> EditDecision(source="llm_smart")
  └── P1: 字幕修正 (模式 A/B) + word-level diff + 时间戳双层断言
         │
Phase 4c: P2 亮点提取 + P3 语义搜索
  ├── P2: 全文分析 -> keep EditDecision + 精华模式视图
  └── P3: 自然语言查询 -> 语义匹配 -> 跳转
         │
Phase 4d: 集成测试 + 发布
  ├── 端到端集成测试 (TaskManager 全链路)
  ├── Topic Drift 旧代码清理
  └── 构建验证 + 发布
```

| 阶段 | 内容 | 预估 | 依赖 |
|------|------|------|------|
| **4a** | L-01/L-02/L-03 + 多 Timeline 基础设施 | 6-7 pd | 无 |
| **4b** | C-02 + P0 + P1 | 5-7 pd | 4a 完成 |
| **4c** | P2 + P3 | 5-6 pd | 4b 完成 (P1 字幕质量) |
| **4d** | 集成测试 + 发布 | 2-3 pd | 4a-4c 完成 |
| **合计** | | **18-23 pd** | |

> 注: 相比原审计预估 (16-21 pd)，因工程化前置独立为 4a 组成部分，总工期增加 2 pd。这是反馈要求的「重构前测试套件稳定」的必要投入。

---

## 3. Phase 4a: 工程化前置 + 多 Timeline 基础设施

> 预估: 6-7 pd
> 目标: 在大规模 LLM 重构前，建立自动化约束 (Lint + Mock 工厂 + API 检查)，并完成多 Timeline 数据模型与 ProjectService 重构。

### 3.1 L-01: Lint 工具链引入 (1 pd)

**问题回顾:** 项目无 ESLint，Python 无 ruff，仅靠 `vue-tsc --noEmit` 做类型检查。M-02 类 import 别名违规无自动化防护。

#### 3.1.1 Python: ruff

**新增 `pyproject.toml` 配置:**

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"
```

**实施步骤:**

1. `uv add --dev ruff`
2. 写入上述 `[tool.ruff]` 配置到 `pyproject.toml`
3. `uv run ruff check . --fix` 全量修复 (预期大量 import 排序自动修复)
4. `uv run ruff format .` 统一格式
5. 人工 review 无法自动修复的项 (预计 < 10 处)
6. 在 `pyproject.toml` 添加 `[tool.pytest.ini_options]` (当前缺失):
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   markers = [
       "integration: end-to-end tests requiring full task pipeline",
   ]
   ```

**验收标准:**
- `uv run ruff check .` 零错误
- `uv run ruff format --check .` 零差异
- 现有 ~135 测试全部通过

#### 3.1.2 前端: ESLint + `no-restricted-imports`

**新增 `frontend/eslint.config.js` (flat config):**

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import vue from "eslint-plugin-vue";

export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    files: ["**/*.{ts,vue}"],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [
          {
            group: ["../*", "../../*"],
            message: "Use @/ alias instead of relative paths. See CLAUDE.md convention."
          }
        ]
      }]
    }
  },
  {
    ignores: ["dist/**", "node_modules/**", "frontend_dist/**"]
  }
];
```

**实施步骤:**

1. `cd frontend && bun add -d eslint @eslint/js typescript-eslint eslint-plugin-vue`
2. 写入 `eslint.config.js`
3. `bunx eslint . --fix` 全量修复
4. `package.json` 添加 scripts:
   ```json
   "lint": "eslint .",
   "lint:fix": "eslint . --fix"
   ```
5. 在 `build` script 前置 `bun run lint` (与现有 `prebuild` 并列)

**验收标准:**
- `cd frontend && bun run lint` 零错误
- M-02 类违规 (相对路径 import) 被规则拦截
- `bun run build` 仍成功

---

### 3.2 L-02: 测试 Mock 工厂抽离 (1.5 pd)

**问题回顾:** 后端各测试文件内联 `monkeypatch.setattr` / `patch()`，前端各 `.test.ts` 内联构造 `Project` 对象。模型字段变更需手动同步多处。

#### 3.2.1 后端 Mock 工厂

**新增 `tests/mocks/__init__.py` + `tests/mocks/factories.py`:**

```python
"""Centralized test mock factories.

All test data construction should go through these factories to avoid
field-sync issues when models change (see audit L-02).
"""
from core.models import (
    Project, ProjectMeta, Segment, EditDecision, TranscriptData,
    AnalysisData, AnalysisResult, TopicDriftData, MediaInfo, SegmentType,
)
from tests.mocks.fixtures import SAMPLE_SRT_CONTENT, SAMPLE_SEGMENTS_RAW


def make_segment(
    *,
    id: str = "s1",
    type: SegmentType = SegmentType.SUBTITLE,
    start: float = 0.0,
    end: float = 5.0,
    text: str = "sample text",
    **kwargs,
) -> Segment:
    """Build a Segment with sensible defaults."""
    return Segment(id=id, type=type, start=start, end=end, text=text, **kwargs)


def make_edit_decision(
    *,
    id: str = "e1",
    target_id: str = "s1",
    action: str = "delete",
    source: str = "manual",
    status: str = "pending",
    **kwargs,
) -> EditDecision:
    return EditDecision(id=id, target_id=target_id, action=action,
                       source=source, status=status, **kwargs)


def make_project(
    *,
    segments: list[Segment] | None = None,
    edits: list[EditDecision] | None = None,
    name: str = "test-project",
    **kwargs,
) -> Project:
    """Build a complete Project with all required fields populated.

    Any field added to Project in the future only needs to be updated here,
    not in every test file.
    """
    segs = segments if segments is not None else [make_segment()]
    return Project(
        project=ProjectMeta(name=name),
        transcript=TranscriptData(segments=segs),
        edits=edits if edits is not None else [],
        **kwargs,
    )


def make_llm_response(content: str, usage: dict | None = None) -> dict:
    """Build a mock call_llm return value."""
    return {
        "success": True,
        "data": {
            "content": content,
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    }
```

**实施步骤:**

1. 创建 `tests/mocks/` 目录 + `__init__.py`
2. 编写 `factories.py` (上述 `make_*` 函数)
3. 抽离 `tests/conftest.py` 中的数据 fixtures 到 `tests/mocks/fixtures.py`
4. 逐文件迁移: `test_project_service.py`, `test_topic_drift.py`, `test_llm_service.py` 等，将内联构造替换为工厂调用
5. 迁移后运行全量测试确认无回归

**验收标准:**
- `tests/mocks/factories.py` 存在且被 ≥ 5 个测试文件引用
- `grep -r "Segment(id=" tests/*.py` 的直接构造减少 ≥ 70%
- 全量测试通过

#### 3.2.2 前端 Mock 工厂

**新增 `frontend/src/test/helpers/mockProject.ts`:**

```typescript
import type {
  Project, Segment, EditDecision, TopicDriftData, AnalysisData,
} from "@/types/project";

export function mockSegment(overrides: Partial<Segment> = {}): Segment { ... }
export function mockEditDecision(overrides: Partial<EditDecision> = {}): EditDecision { ... }
export function mockProject(overrides: Partial<Project> = {}): Project {
  return {
    project: { name: "test", created_at: "", ... },
    media: null,
    transcript: { engine: "whisper", language: "zh", segments: [mockSegment()] },
    analysis: { last_run: null, results: [] },
    edits: [],
    topic_drift: { topic_description: "", results: [], transcript_hash: "", last_run: null, token_usage: {} },
    ...overrides,
  };
}
```

**实施步骤:**

1. 创建 `frontend/src/test/helpers/mockProject.ts`
2. 迁移 `useSegmentEdit.test.ts`, `TopicDriftPanel.test.ts` 等的内联 mock
3. `bun run test` 确认通过

**验收标准:**
- `mockProject.ts` 存在且被 ≥ 3 个测试文件引用
- 前端测试全部通过

---

### 3.3 L-03: 前后端 API 同步检查脚本 (0.5 pd)

**问题回顾:** 79 个 `@expose` 方法与前端 `call()` 调用纯人工同步，M-03 第 2 项因此复发。

**新增 `scripts/check_api_sync.py`:**

```python
#!/usr/bin/env python
"""Check that frontend call() invocations match backend @expose methods.

Usage: uv run python scripts/check_api_sync.py
Exit code 0 = in sync, 1 = mismatch.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

def extract_expose_methods() -> set[str]:
    """Parse main.py for @expose-decorated method names."""
    main_py = ROOT / "main.py"
    methods = set()
    for match in re.finditer(r'@expose\s*\n\s*def (\w+)', main_py.read_text(encoding="utf-8")):
        methods.add(match.group(1))
    return methods

def extract_frontend_calls() -> set[str]:
    """Parse frontend/src for call<T>("method_name", ...) invocations."""
    call_pattern = re.compile(r'call<[^>]*>\(\s*"([^"]+)"')
    methods = set()
    for ts_file in (ROOT / "frontend" / "src").rglob("*.{ts,vue}"):
        methods.update(call_pattern.findall(ts_file.read_text(encoding="utf-8")))
    return methods

def main() -> int:
    exposed = extract_expose_methods()
    called = extract_frontend_calls()
    missing_expose = called - exposed  # frontend calls but backend doesn't expose
    unused_expose = exposed - called   # backend exposes but no frontend call (warning)
    if missing_expose:
        print(f"ERROR: Frontend calls methods not @expose'd in main.py: {sorted(missing_expose)}")
        return 1
    if unused_expose:
        print(f"WARN: @expose methods with no frontend call() (may be legitimate): {sorted(unused_expose)}")
    print(f"OK: {len(called)} frontend calls verified against {len(exposed)} @expose methods")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**实施步骤:**

1. 创建 `scripts/check_api_sync.py`
2. `pyproject.toml` 或根目录添加便捷入口
3. `package.json` 添加 `"check:api": "cd .. && uv run python scripts/check_api_sync.py"`
4. 首次运行，修复已存在的不一致 (预期 0，因 M-03 已解决)

**验收标准:**
- `uv run python scripts/check_api_sync.py` 输出 `OK` 并返回 0
- 手动在 `main.py` 删除一个 `@expose`，脚本能检测到并报错

---

### 3.4 多 Timeline 基础设施 (3-4 pd)

> 这是 P0-P3 的共同前置依赖。审计反馈指出原预估 4-5 pd 略显乐观，本计划按 3-4 pd 估算 (不含工程化前置已完成的 mock 工厂支持)，重点在于 `ProjectService` 适配器改造与迁移安全性。

#### 3.4.1 风险评估 (基于反馈)

| 风险 | 反馈指出 | 缓解措施 |
|------|----------|----------|
| 估算乐观 | 涉及存储层迁移 + 全量 API 适配 + 前端 UI 状态切换 | 引入 `active_timeline` property 适配器，机械替换 ~49 处引用，降低风险 |
| 测试套件崩溃 | 大规模重构 | **已前置 L-02** (3.2)，mock 工厂保证测试稳定 |
| 向后兼容 | 现有项目加载 | 自动迁移: 现有 `transcript/edits/analysis` 包装为 `id="default"` timeline |

#### 3.4.2 数据模型 (`core/models.py`)

**新增 `Timeline` 模型:**

```python
class Timeline(BaseModel, frozen=True):
    """独立时间线 -- 拥有完整的 transcript + edits + analysis。

    每个 Timeline 是封闭的三元组 (transcript, edits, analysis)，
    切换时互不影响。LLM 操作在 fork 出的 Timeline 上进行，原始不受影响。
    """
    id: str                          # 唯一标识 ("default" / "字幕修正-v1" / "智能删除-v2")
    label: str                       # 用户可见名称
    source: str = "manual"           # 创建来源 ("manual" / "fork" / "llm_p0" / "llm_p1")
    created_at: str                  # ISO 时间戳
    parent_id: str = ""              # 分叉来源 (空 = 根 timeline)
    transcript: TranscriptData = Field(default_factory=TranscriptData)
    edits: list[EditDecision] = Field(default_factory=list)
    analysis: AnalysisData = Field(default_factory=AnalysisData)
```

**`Project` 模型改造:**

```python
class Project(BaseModel, frozen=True):
    schema_version: int = 2          # 从 1 升级到 2
    project: ProjectMeta = Field(default_factory=ProjectMeta)
    media: MediaInfo | None = None

    # 新增: 多 Timeline 容器
    timelines: list[Timeline] = Field(default_factory=list)
    active_timeline_id: str = "default"

    # 移除: 原扁平字段 (通过迁移转为 default timeline)
    # transcript: TranscriptData     <- 移除
    # analysis: AnalysisData         <- 移除
    # edits: list[EditDecision]      <- 移除
    # topic_drift: TopicDriftData    <- 移除 (P0 重构后不再需要独立字段)
```

**关键设计决策:**

1. **`topic_drift` 字段移除**: P0 重构后 Topic Drift 旧逻辑删除，`TopicDriftData`/`TopicDriftResult` 模型随之移除。迁移时旧 `topic_drift` 数据丢弃 (不影响核心功能)。
2. **每条 Timeline 独立 transcript**: P1 字幕修正在目标 timeline 的 transcript 上直接操作 (改 text / 合并句 / 拆分句)，不通过 overlay 叠加。segment ID 体系在 timeline 内部自洽。
3. **`active_timeline` 只读 property**: `ProjectService` 通过它访问当前 timeline 的 transcript/edits/analysis，替代原 `self._current.transcript` 等。

#### 3.4.3 迁移逻辑 (`ProjectService._migrate_project`)

**在 `open_project` 加载 JSON 后、构造 `Project` 前执行迁移:**

```python
def _migrate_to_v2(self, raw: dict) -> dict:
    """Migrate schema_version 1 -> 2: wrap flat fields into default Timeline."""
    if raw.get("schema_version", 1) >= 2:
        return raw

    # 提取 v1 扁平字段
    transcript = raw.pop("transcript", {})
    edits = raw.pop("edits", [])
    analysis = raw.pop("analysis", {})
    raw.pop("topic_drift", None)  # 丢弃旧 Topic Drift 数据

    # 包装为 default timeline
    raw["timelines"] = [{
        "id": "default",
        "label": "原始",
        "source": "migrated",
        "created_at": raw.get("project", {}).get("created_at", ""),
        "parent_id": "",
        "transcript": transcript,
        "edits": edits,
        "analysis": analysis,
    }]
    raw["active_timeline_id"] = "default"
    raw["schema_version"] = 2
    return raw
```

**迁移测试 (使用 L-02 mock 工厂):**

```python
def test_migrate_v1_to_v2_preserves_transcript():
    v1_data = mock_v1_project(segments=[mock_segment_dict(id="s1")])
    migrated = service._migrate_to_v2(v1_data)
    assert migrated["schema_version"] == 2
    assert len(migrated["timelines"]) == 1
    assert migrated["timelines"][0]["id"] == "default"
    assert migrated["active_timeline_id"] == "default"
    # transcript 完整保留
    assert migrated["timelines"][0]["transcript"]["segments"][0]["id"] == "s1"

def test_migrate_v2_passthrough():
    v2_data = mock_v2_project()
    assert service._migrate_to_v2(v2_data) is v2_data  # 不变
```

#### 3.4.4 `ProjectService` 适配器改造

**核心: 新增 `active_timeline` property，统一替换 ~49 处引用。**

```python
class ProjectService:
    @property
    def active_timeline(self) -> Timeline:
        """当前激活的 Timeline。所有 transcript/edits/analysis 操作通过此访问。"""
        if not self._current:
            raise RuntimeError("No project loaded")
        tl_id = self._current.active_timeline_id
        for tl in self._current.timelines:
            if tl.id == tl_id:
                return tl
        # 容错: active_timeline_id 无匹配时回退到第一个
        return self._current.timelines[0]

    # 机械替换规则 (sed 级别):
    # self._current.transcript  ->  self.active_timeline.transcript
    # self._current.edits       ->  self.active_timeline.edits
    # self._current.analysis    ->  self.active_timeline.analysis
```

**改造范围 (基于代码扫描，~49 处):**

| 方法 | 行号 | 引用类型 |
|------|------|----------|
| `_migrate_silence_edits` | 140-171 | transcript + edits |
| `update_transcript` | 229-256 | transcript + edits |
| `_trim_silences_around_subtitles` | 333-398 | transcript + edits |
| `add_silence_results` | 400-490 | transcript + edits + analysis |
| `update_edit_decision` | 492-516 | edits |
| `update_segment` | 518-566 | transcript + edits |
| `update_segment_text` | 568-589 | transcript |
| `add_segment` / `delete_segment` / `clear_subtitles` | 591-668 | transcript + edits |
| `merge_segments` / `split_segment` | 711-800 | transcript + edits |
| `search_replace` / `mark_segments` | 802-901 | transcript + edits |
| `add_analysis_results` | 1013-1059 | analysis + transcript + edits |
| `generate_subtitle_keep_ranges` | 1109-1199 | transcript + edits |
| ... | (其余见 Appendix B) | ... |

**改造策略:** 由于 `Timeline` 与原 `Project` 持有相同结构的 `transcript/edits/analysis`，且 Pydantic `frozen=True` 的 `model_copy(update=...)` 模式不变，替换是**纯机械的属性路径变更**。但需注意: 更新 timeline 后需将整个 `timelines` 列表替换回 `self._current` (因为 frozen model 不可变)。

**辅助方法:**

```python
def _update_active_timeline(self, **updates) -> None:
    """更新当前 timeline 并写回 Project.timelines。"""
    tl = self.active_timeline
    new_tl = tl.model_copy(update=updates)
    new_timelines = [
        new_tl if t.id == tl.id else t
        for t in self._current.timelines
    ]
    self._current = self._current.model_copy(update={"timelines": new_timelines})
```

所有原 `self._current = self._current.model_copy(update={"transcript": new_t})` 改为 `self._update_active_timeline(transcript=new_t)`。

#### 3.4.5 Timeline 操作 API (`ProjectService` 新增方法 + `main.py` expose)

```python
# ProjectService 新增
def create_timeline(self, label: str, source: str = "manual",
                    fork_from: str | None = None) -> dict:
    """新建空白或从指定 timeline 分叉。"""
    tl_id = f"tl_{int(time.time()*1000)}"  # 毫秒时间戳保证唯一
    if fork_from:
        parent = self._find_timeline(fork_from)
        new_tl = Timeline(id=tl_id, label=label, source=source,
                         created_at=iso_now(), parent_id=fork_from,
                         transcript=parent.transcript,
                         edits=[e.model_copy() for e in parent.edits],
                         analysis=parent.analysis.model_copy(deep=True))
    else:
        new_tl = Timeline(id=tl_id, label=label, source=source,
                         created_at=iso_now())
    # 追加 + 切换
    ...

def switch_timeline(self, timeline_id: str) -> dict: ...
def delete_timeline(self, timeline_id: str) -> dict: ...  # 至少保留一条
def rename_timeline(self, timeline_id: str, new_label: str) -> dict: ...
def duplicate_timeline(self, timeline_id: str, new_label: str) -> dict: ...
```

**`main.py` 暴露:**

```python
@expose
def create_timeline(self, label: str, source: str = "manual",
                    fork_from: str | None = None) -> dict:
    return self._project.create_timeline(label, source, fork_from)

@expose
def switch_timeline(self, timeline_id: str) -> dict: ...
@expose
def delete_timeline(self, timeline_id: str) -> dict: ...
@expose
def rename_timeline(self, timeline_id: str, new_label: str) -> dict: ...
@expose
def duplicate_timeline(self, timeline_id: str, new_label: str) -> dict: ...
```

#### 3.4.6 前端: Timeline 切换器 UI

**新增组件 `frontend/src/components/workspace/TimelineSwitcher.vue`:**

- 下拉/标签页式切换器，显示所有 timeline 的 label
- 「新建 Timeline」按钮 (可选 fork 源)
- 切换时触发 `switch_timeline` API 调用，刷新全局 Project 状态
- 当前 active timeline 高亮

**`WorkspacePage.vue` 改造:**

- 顶部工具栏嵌入 `TimelineSwitcher`
- 所有 `project.transcript` / `project.edits` / `project.analysis` 引用改为 `activeTimeline.transcript` 等
- 新增 computed `activeTimeline` 从 `project.timelines` 中按 `active_timeline_id` 过滤

**类型定义 (`frontend/src/types/project.ts`):**

```typescript
export interface Timeline {
  id: string
  label: string
  source: string
  created_at: string
  parent_id: string
  transcript: TranscriptData
  edits: EditDecision[]
  analysis: AnalysisData
}

export interface Project {
  schema_version: number
  project: ProjectMeta
  media: MediaInfo | null
  timelines: Timeline[]
  active_timeline_id: string
  // 移除: transcript, edits, analysis, topic_drift
}
```

#### 3.4.7 Phase 4a 验收标准

| 验收项 | 标准 |
|--------|------|
| 模型 | `Timeline` 存在，`Project.timelines` + `active_timeline_id` 存在 |
| 迁移 | v1 `project.json` 加载后自动转为单 default timeline，数据无损 |
| ProjectService | `active_timeline` property 工作，~49 处引用全部替换，现有功能不回归 |
| API | 5 个 timeline 操作方法在 `main.py` `@expose`，前端 `call()` 可调 |
| UI | `TimelineSwitcher` 可切换，切换后 transcript/波形/SuggestionPanel 全部刷新 |
| 测试 | 新增迁移测试 + timeline CRUD 测试，全量测试通过 |
| Lint | ruff + ESLint 零错误 |

---

## 4. Phase 4b: C-02 解决 + P0 智能删除增强 + P1 字幕修正

> 预估: 5-7 pd
> 依赖: Phase 4a 完成 (多 Timeline + 工程化前置)
> 目标: 解决 LLM 格式不对称，将 Topic Drift 重构为 P0 (补规则引擎盲区) + P1 (ASR 字幕修正)

### 4.1 C-02: LLM 输入结构化 + 输出分层降级 (1 pd)

> 解决审计 C-02 (OPEN)。这是 P0/P1 的共同基础 -- LLM 交互框架的格式化改造。

#### 4.1.1 输入端: 结构化 JSON messages

**改造 `core/llm_service.py`，新增通用结构化输入构建器:**

```python
def _build_structured_user_message(
    segments: list[dict],
    extra_context: dict | None = None,
) -> str:
    """Build structured JSON user message for LLM analysis.

    Replaces ad-hoc [id] text formatting with JSON, eliminating
    segment_id parsing ambiguity and special-character breakage.
    """
    payload = {
        "segments": [
            {"id": s.get("id", s.get("segment_id", "?")),
             "text": s.get("text", "").strip(),
             "start": s.get("start"),
             "end": s.get("end")}
            for s in segments
        ],
    }
    if extra_context:
        payload.update(extra_context)
    return json.dumps(payload, ensure_ascii=False)
```

**system prompt 改为纯输出格式说明:**

```
你是视频内容分析专家。用户会以 JSON 格式提供转录片段列表。
{task_specific_instruction}
输出格式: JSON 数组，每个元素 {output_schema}
```

#### 4.1.2 输出端: 4 层降级解析

**新增 `core/llm_service.py:_parse_json_response_layers`:**

```python
def _parse_json_response_layers(content: str) -> list[dict] | None:
    """4-layer degraded JSON parsing for cross-provider robustness.

    Layer 1: Direct json.loads (fastest, model follows format)
    Layer 2: Extract markdown code block then json.loads
    Layer 3: Regex extract [...] or {...} substring then json.loads
    Layer 4: Line-by-line regex extract key fields (extreme fallback)
    Returns None if all layers fail.
    """
    import re

    # Layer 1: Direct parse
    try:
        result = json.loads(content.strip())
        return result if isinstance(result, list) else [result]
    except (json.JSONDecodeError, ValueError):
        pass

    # Layer 2: Markdown code block
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
    if md_match:
        try:
            result = json.loads(md_match.group(1).strip())
            return result if isinstance(result, list) else [result]
        except (json.JSONDecodeError, ValueError):
            pass

    # Layer 3: Regex extract array/object
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1:
        try:
            return json.loads(content[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            pass
    # Also try object
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1:
        try:
            result = json.loads(content[start:end + 1])
            return result if isinstance(result, list) else [result]
        except (json.JSONDecodeError, ValueError):
            pass

    # Layer 4: Line-by-line fallback
    items = []
    pattern = re.compile(r'"segment_id"\s*:\s*"([^"]+)".*?"relevance"\s*:\s*([\d.]+)')
    for match in pattern.finditer(content):
        items.append({"segment_id": match.group(1),
                      "relevance": float(match.group(2))})
    return items if items else None
```

#### 4.1.3 可选: provider 能力适配 `response_format`

**改造 `core/llm_service.py:call_llm`:**

```python
def call_llm(prompt: str, *, system: str = "", config: LlmConfig | None = None,
             json_mode: bool = False, ...) -> dict:
    ...
    kwargs = {"model": model, "messages": messages, ...}

    # 仅对支持 json_object 的 provider 启用 (OpenAI/DeepSeek)
    if json_mode and config.provider in (LlmProvider.OPENAI, LlmProvider.DEEPSEEK):
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    ...
```

#### 4.1.4 验收标准

| 验收项 | 标准 |
|--------|------|
| 输入结构化 | `_build_structured_user_message` 生成合法 JSON，segment_id 无歧义 |
| 输出分层 | 4 层降级解析，每层独立测试用例覆盖 |
| 旧代码 | `_TOPIC_DRIFT_USER_TEMPLATE` / `_build_topic_drift_prompt` / `_parse_topic_drift_response` 删除或标记废弃 |
| provider 适配 | OpenAI/DeepSeek 启用 `json_object`，其他 provider 仅依赖 prompt 约束 + 分层解析 |
| 测试 | 新增 4 层解析的单元测试 + 跨 provider mock 测试 |

---

### 4.2 P0: 智能删除增强 (2 pd)

> LLM 补全规则引擎漏掉的「可安全删除」片段，直接生成 EditDecision，与规则结果合并展示。

#### 4.2.1 设计要点

| 维度 | 决策 |
|------|------|
| 分析窗口 | **短窗口 15-30s**，因为口误/重复/口癖都是局部现象。新增 `chunk_transcript_short` (区别于现有 5min `chunk_transcript`) |
| 输出形式 | 直接生成 `EditDecision(action="delete", source="llm_smart")`，复用现有 SuggestionPanel |
| 增量分析 | 跳过规则引擎已标记的 segment (`analysis.results` 中已有的 segment_ids) |
| 展示 | 与规则结果同列，`source` 字段区分，用户统一 confirm/reject |
| 时间戳 | **不改**: start/end 来自已有 segment，只生成删除建议 |

#### 4.2.2 LLM 任务定义

**新增 `core/llm_service.py:analyze_smart_delete`:**

```python
_SMART_DELETE_SYSTEM = """你是视频剪辑助手。用户以 JSON 提供一组转录片段。
请识别其中可安全删除的片段:
1. 语义重复: 同一观点换措辞重述 (规则引擎只能识别字面重复)
2. 无触发词口误: 说错后自然纠正的完整区域 (规则引擎只能识别"不对/重来"触发词)
3. 上下文口头禅: 无实义过渡句如"然后接下来就是我们要讲的那个"

输出格式: JSON 数组
[{"segment_id": "片段ID", "action": "delete", "reason": "删除理由", "category": "semantic_dup|self_correct|filler_phrase"}]
只输出建议删除的片段，无需删除的不要输出。
"""

def analyze_smart_delete(
    segments: list[dict],
    existing_flagged_ids: set[str] | None = None,  # 跳过规则引擎已标记的
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
) -> dict[str, Any]:
    """Short-window LLM analysis to catch what the rule engine misses."""
    # 1. 过滤已标记 segment
    # 2. 短窗口分块 (chunk_transcript_short, 15-30s)
    # 3. 结构化 JSON 输入 (4.1.1)
    # 4. 调用 LLM + 4 层降级解析 (4.1.2)
    # 5. 返回删除建议列表
```

#### 4.2.3 集成到现有流程

**`main.py` 新增任务类型 + handler:**

```python
# models.py TaskType 枚举新增
# SMART_DELETE = "smart_delete"

# main.py
def _handle_smart_delete(self, task: MiloTask, cancel_event, progress_cb) -> dict:
    timeline = self._project.active_timeline
    segments = [s.model_dump() for s in timeline.transcript.segments
                if s.type == SegmentType.SUBTITLE]

    # 规则引擎已标记的 segment_ids
    existing_ids = set()
    for result in timeline.analysis.results:
        existing_ids.update(result.segment_ids)

    result = analyze_smart_delete(segments, existing_ids,
                                  cancel_event=cancel_event, progress_cb=progress_cb)
    if result["success"]:
        # 直接转为 EditDecision
        edits = [_smart_delete_result_to_edit(r, source="llm_smart")
                 for r in result["data"]["results"]]
        self._project.add_analysis_results(edits, source="llm_smart")
    return result
```

#### 4.2.4 Topic Drift 旧代码清理

| 文件 | 处理 |
|------|------|
| `core/llm_service.py:289-493` | `_TOPIC_DRIFT_SYSTEM` / `_TOPIC_DRIFT_USER_TEMPLATE` / `_build_topic_drift_prompt` / `_parse_topic_drift_response` / `analyze_topic_drift` **删除** |
| `core/models.py:251-267` | `TopicDriftResult` / `TopicDriftData` **删除** |
| `frontend/src/components/workspace/TopicDriftPanel.vue` | **删除** |
| `frontend/src/composables/useTopicDrift.ts` | 泛化为 `useLlmAnalysis.ts` (保留流式进度框架) |
| `frontend/src/composables/useLlmAnalysis.ts` | 重命名/泛化为通用 LLM 分析 composable (P0/P1/P2 共用) |
| `main.py:633-691, 1562-1590` | `_handle_topic_drift` / `start_topic_drift` / `get_topic_drift_results` **删除** |

#### 4.2.5 验收标准

| 验收项 | 标准 |
|--------|------|
| 功能 | P0 能识别语义重复 / 无触发词口误 / 上下文口头禅，生成 EditDecision |
| 集成 | 结果出现在 SuggestionPanel，source="llm_smart" 可区分，支持「信任此来源」批量 confirm 高置信度建议 |
| 增量 | 不重复分析规则引擎已标记的 segment |
| 旧代码 | Topic Drift 相关代码/组件/模型全部删除 |
| 测试 | P0 分析逻辑单元测试 + mock LLM 响应测试 |

> **批量信任功能 (反馈 4 采纳):** P0 和 P1 的 LLM 建议都面临用户「确认负担重」的问题。SuggestionPanel 和 SubtitleCorrectionReview 均新增「信任此来源 (Accept all from source)」按钮:
> - 用户点击后，一键 accept 该 `source` 下所有非 `low_confidence` 的建议
> - 高置信度建议批量应用，低置信度仍需逐条确认
> - 例如: 用户觉得某模型 P0 表现好，一键接受所有 `source="llm_smart"` 且置信度达标的删除建议
> - 实现: `ProjectService` 新增 `confirm_all_from_source(source: str, min_confidence: float = 0.0)` 方法

---

### 4.3 P1: 字幕修正 (3-4 pd)

> ASR 字幕纠错，解决 Milo-Cut 最大痛点。支持无参考稿 (LLM 自主纠错) 和有参考稿 (对齐修正) 两种模式。

#### 4.3.1 两种修正模式

**模式 A: 无参考稿 (LLM 自主纠错)**

```python
def analyze_subtitle_correction(
    segments: list[dict],
    reference_text: str | None = None,  # None = 模式 A, 非空 = 模式 B
    context_window: int = 3,            # 反馈建议: 前后 2-3 segment 辅助判断同音词
    *,
    config: LlmConfig | None = None,
    ...
) -> dict[str, Any]:
```

**模式 B: 有参考稿 (逐字稿对齐)**

- 输入增加 `reference_text` (全文)
- LLM 任务: 将 ASR 字幕与参考稿对齐，用参考稿内容修正 ASR 文本
- 输出: 修正后文本 + 对齐置信度

**反馈补充点 (已采纳):** 增加 `context_window` 参数。单 segment 很短，LLM 需要前后 2-3 个 segment 判断同音词 (如「由于」vs「优化」)。输入端在 `_build_structured_user_message` 时附带上下文 segment。

#### 4.3.2 时间戳安全保证 (核心约束)

> 审计 C-01 P1 节 + 反馈补充的断言层。

**数据流:**

```
原 segment (start/end 不变, words 原始)
       │
       ▼
LLM 修正文本
       │
       ▼
word-level diff 对齐 (difflib)
       │
       ├── 对齐成功 → 保留/重建 words 数组
       └── 对齐失败 → 清空 words, 标记 dirty_flags.llm_corrected
       │
       ▼
时间戳断言层 (双层: dev raise / prod warn)
       │
       ├── start/end 未变 → 通过
       └── start/end 变了 → dev: raise ValueError / prod: warn + 回滚文本
       │
       ▼
写入 active_timeline.transcript (只改 text + words + dirty_flags)
```

**时间戳断言层实现 (`core/llm_service.py` + `core/project_service.py`):**

```python
import os

def _assert_timestamps_unchanged(
    original: Segment, corrected: Segment, *, segment_id: str
) -> None:
    """Double-layer assertion: dev raises, prod warns + rollback signal.

    Ensures subtitle correction NEVER alters start/end physical values.
    """
    if original.start != corrected.start or original.end != corrected.end:
        msg = (f"Timestamp corruption detected on segment {segment_id}: "
               f"start {original.start}->{corrected.start}, "
               f"end {original.end}->{corrected.end}")
        if os.environ.get("MILO_ENV") == "development":
            raise ValueError(msg)
        else:
            logger.warning(msg)
            # 生产环境: 回滚文本修正，保留原始 segment
            raise _TimestampCorruptionError(segment_id, msg)
```

**`ProjectService.apply_subtitle_corrections` 调用断言:**

```python
def apply_subtitle_corrections(self, corrections: list[dict]) -> dict:
    """Apply LLM subtitle corrections to active timeline.

    corrections: [{segment_id, corrected_text, changes: [...]}]
    分层容错策略 (反馈 2.1): 非全量失败，按 segment_id 最大化匹配。
    """
    timeline = self.active_timeline
    seg_map = {s.id: s for s in timeline.transcript.segments}
    total = len(timeline.transcript.segments)

    # --- 分层容错 (反馈 2.1): 不再全量失败，而是最大化匹配 ---
    matched: list[tuple[Segment, dict]] = []
    uncovered_ids: list[str] = []

    for seg in timeline.transcript.segments:
        corr = next((c for c in corrections if c["segment_id"] == seg.id), None)
        if corr:
            matched.append((seg, corr))
        else:
            uncovered_ids.append(seg.id)

    extra_corrections = [c for c in corrections if c["segment_id"] not in seg_map]

    # 场景判定
    if len(matched) == 0:
        return {"success": False, "error": "No segment_id matched (LLM output completely mismatched)"}

    if len(matched) < total:
        # 部分匹配: 应用已匹配的，未覆盖的保留原样并标记
        logger.warning(
            f"Partial correction coverage: {len(matched)}/{total} segments matched, "
            f"{len(uncovered_ids)} uncovered, {len(extra_corrections)} orphaned"
        )

    # 应用修正 (仅 matched)
    new_segments = []
    for seg in timeline.transcript.segments:
        match = next((m for s, m in matched if s.id == seg.id), None)
        if match:
            corrected = seg.model_copy(update={
                "text": match["corrected_text"],
                "dirty_flags": {**seg.dirty_flags, "llm_corrected": True},
            })
            _assert_timestamps_unchanged(seg, corrected, segment_id=seg.id)
            new_segments.append(corrected)
        else:
            # 未覆盖: 保留原样，标记 llm_uncovered 供 UI 高亮
            uncovered = seg.model_copy(update={
                "dirty_flags": {**seg.dirty_flags, "llm_uncovered": True},
            })
            new_segments.append(uncovered)

    self._update_active_timeline(
        transcript=timeline.transcript.model_copy(update={"segments": new_segments}),
        analysis=timeline.analysis.model_copy(update={"last_run": None}),
    )
    return {
        "success": True,
        "data": {
            "corrected_count": len(matched),
            "uncovered_count": len(uncovered_ids),
            "uncovered_ids": uncovered_ids,  # UI 可显示"以下片段未被修正覆盖"
            "orphaned_count": len(extra_corrections),
        },
        "partial": len(matched) < total,  # 标记部分覆盖
    }
```

**字符级 diff 校验 (低置信度标记):**

```python
def _check_correction_confidence(original_text: str, corrected_text: str) -> dict:
    """Flag low-confidence corrections via edit distance threshold."""
    distance = Levenshtein.distance(original_text, corrected_text)
    max_len = max(len(original_text), len(corrected_text), 1)
    ratio = distance / max_len
    return {
        "edit_distance": distance,
        "change_ratio": ratio,
        "low_confidence": ratio > 0.5,  # 超过 50% 字符变更标记低置信度
    }
```

> **1:1 约束容错策略 (反馈 2.1 采纳):**
>
> 原计划的「严格 1:1 失败即报错」在长视频场景有风险: LLM 因 token 限制或解析失败可能输出长度不匹配的数组。改为**分层容错**:
> - **全量匹配** (N=N): 正常应用
> - **部分匹配** (M<N): 按 `segment_id` 最大化匹配已覆盖的，未覆盖的保留原样 + 标记 `dirty_flags.llm_uncovered`，返回 `partial=true` + `uncovered_ids`
> - **全量失配** (0 匹配): 才报错
> - **分段回滚**: 时间戳断言失败的 segment 单独回滚，不影响其他已匹配 segment

#### 4.3.3 Review UI

**新增 `frontend/src/components/workspace/SubtitleCorrectionReview.vue`:**

- 类似 git diff 的逐条 review 界面
- 左侧原始文本，右侧修正文本，变更高亮
- 每条修正显示: `change_ratio` / `low_confidence` 标记 / `category` (同音字/专有名词/断句)
- 用户逐条 accept / reject / 编辑后 accept
- 低置信度修正默认折叠，需手动展开确认
- **未覆盖 segment 提示** (反馈 2.1): 若 `partial=true`，顶部显示「N 个片段未被修正覆盖」+ uncovered 列表
- **批量信任功能** (反馈 4 采纳): 「信任此来源」按钮 -- 一键 accept 所有 `low_confidence: false` 的修正。用户若对当前模型的修正质量满意，可跳过逐条确认。高/低置信度分组显示，批量操作分别适用

#### 4.3.4 验收标准

| 验收项 | 标准 |
|--------|------|
| 模式 A | 无参考稿时 LLM 能修正同音错字/专有名词/断句 |
| 模式 B | 有参考稿时按参考稿对齐修正 |
| 1:1 约束 | 分层容错: 全量匹配正常应用，部分匹配按 segment_id 最大化覆盖 + 标记 uncovered，全量失配才报错 |
| 时间戳安全 | 断言层确保 start/end 不变; dev 环境会 raise，prod 环境 warn + 回滚; 失败 segment 单独回滚不影响其他 |
| word-level diff | 对齐成功保留 words，失败清空 + 标记 dirty_flags.llm_corrected |
| analysis 过期 | 修正后 analysis.last_run = null，UI 提示重新分析 |
| Review UI | 逐条 accept/reject，低置信度标记可见，部分覆盖时显示 uncovered 提示，支持「信任此来源」批量 accept 高置信度修正 |
| 测试 | 时间戳断言测试 (dev/prod 双模式) + diff 对齐测试 + 1:1 约束测试 |

---

## 5. Phase 4c: P2 亮点提取 + P3 语义搜索

> 预估: 5-6 pd
> 依赖: Phase 4b 完成 (P1 字幕质量提升后，P2/P3 结果更准确)
> 目标: 从「减法」(删差的) 到「加法」(挑好的)，并提供自然语言导航

### 5.1 P2: 智能亮点提取 (3-4 pd)

> LLM 分析全文，自动提取高信息密度片段，生成「精华版」时间线。

#### 5.1.1 设计要点

| 维度 | 决策 |
|------|------|
| 分析范围 | **全文** (非短窗口)。需要 LLM 理解整体结构才能判断哪些是核心论点 |
| 分块策略 | 复用现有 `chunk_transcript` (5min chunk)，但 LLM 任务改为「标记高信息密度段落」 |
| 输出形式 | 生成 `EditDecision(action="keep", source="llm_highlight")`，反转现有 delete 逻辑 |
| 目标时长 | 用户可调整 (如「生成 10 分钟精华版」)，LLM 按比例裁剪 |
| Timeline 集成 | 建议在 **fork 出的新 timeline** 上操作，保留原始完整 timeline |

#### 5.1.2 LLM 任务定义

```python
_HIGHLIGHT_SYSTEM = """你是演讲视频内容分析师。用户以 JSON 提供完整转录。
请识别高信息密度片段 (核心论点、关键数据、精彩类比、重要结论)，
用于生成精华版剪辑。

输出格式: JSON 数组
[{"segment_id": "片段ID", "highlight_reason": "亮点理由", "density": "high|medium"}]

用户会指定目标精华时长，请按信息密度优先级选取，总时长尽量接近目标。
"""

def analyze_highlights(
    segments: list[dict],
    target_duration_minutes: int = 10,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
) -> dict[str, Any]:
    """Full-transcript analysis to extract highlight segments."""
    # 1. 全文分块 (5min chunk + 30s overlap)
    # 2. 结构化 JSON 输入 + target_duration 上下文
    # 3. 逐块调用 LLM，汇总 highlight 结果
    # 4. 按密度排序，按 target_duration 裁剪
    # 5. 返回 keep 建议列表
```

#### 5.1.3 精华模式视图

**新增 `frontend/src/components/workspace/HighlightModeView.vue`:**

- 切换到精华模式后，非 highlight segment 变灰/折叠
- highlight segment 高亮显示 + 显示 `highlight_reason`
- 顶部显示: 已选时长 / 目标时长，超量时提示
- 用户可手动添加/移除 highlight，实时更新总时长
- 「导出精华版」按钮: 仅导出 keep 的 segment
- **跳变点提示** (反馈 2.2): 相邻 highlight 间隔过远的拼接点标记为 jump_cut，UI 显示警告图标 + 原始间隔时长

#### 5.1.4 跳变点处理 (反馈 2.2)

> P2 导出的精华版将多个 highlight segment 拼接，若两个 highlight 在原视频中相距甚远，直接拼接会产生突兀的音频爆音。

**检测逻辑 (`core/export_service.py` 导出时):**

```python
def _detect_jump_cuts(highlight_segments: list[Segment], threshold_s: float = 2.0) -> list[dict]:
    """检测需要转场处理的跳变点。

    Args:
        highlight_segments: 按 start 排序的 keep segment 列表
        threshold_s: 两个 highlight 在原视频中间隔超过此值视为跳变点
    Returns: [{index, gap_duration, from_end, to_start}, ...]
    """
    jump_cuts = []
    for i in range(len(highlight_segments) - 1):
        current = highlight_segments[i]
        next_seg = highlight_segments[i + 1]
        gap = next_seg.start - current.end
        if gap > threshold_s:
            jump_cuts.append({
                "index": i,
                "gap_duration": gap,
                "from_end": current.end,
                "to_start": next_seg.start,
            })
    return jump_cuts
```

**导出选项 (`export_service.py`):**

| 跳变点处理选项 | 说明 | FFmpeg 实现 |
|----------------|------|-------------|
| `none` (默认) | 直接拼接，无转场 | concat demuxer |
| `crossfade` | 音频淡入淡出，消除爆音 | `afade=out` + `afade=in` (0.3s) |
| `smart` | 保留跳跃感，仅处理音频爆音 | 仅音频 crossfade，视频硬切 |

**元数据输出:** 导出结果附带 `jump_cuts` 列表，记录每个跳变点的间隔时长，用户可在导出前预览哪些拼接点会有突兀感。

#### 5.1.5 验收标准

| 验收项 | 标准 |
|--------|------|
| 功能 | P2 能识别高信息密度片段，生成 keep EditDecision |
| 时长控制 | 按目标时长裁剪，实际时长在目标 ±20% 内 |
| 精华模式 | UI 切换后高亮/折叠正确，可手动调整 |
| 导出 | 「导出精华版」仅包含 keep segment，跳变点可选 crossfade/smart/none |
| 跳变点 | 间隔 >2s 的拼接点标记 jump_cut，导出选项可处理音频爆音 |
| 测试 | P2 分析逻辑测试 + 时长裁剪算法测试 + 跳变点检测测试 |

---

### 5.2 P3: 语义搜索 (2 pd)

> 自然语言搜索转录内容，快速定位特定段落。

#### 5.2.1 设计要点

| 维度 | 决策 |
|------|------|
| 匹配方式 | **LLM 语义匹配** (非 embedding 向量检索，避免引入向量数据库依赖) |
| 查询范围 | 当前 active timeline 的全部 segment |
| 返回 | 最相关的 N 个 segment (默认 5)，按相关度排序 |
| 交互 | 搜索框输入自然语言 -> 结果列表 -> 点击跳转 |

#### 5.2.2 LLM 任务定义

```python
def semantic_search(
    query: str,
    segments: list[dict],
    top_k: int = 5,
    *,
    config: LlmConfig | None = None,
) -> dict[str, Any]:
    """Natural language search over transcript segments.

    Returns top_k most relevant segments with relevance scores.
    """
    _SEARCH_SYSTEM = """你是内容检索助手。用户以 JSON 提供转录片段列表和搜索查询。
    请找出与查询语义最相关的片段 (不仅是字面匹配，包括语义关联)。
    输出格式: JSON 数组，按相关度降序
    [{"segment_id": "片段ID", "relevance": 0.0-1.0, "match_reason": "匹配原因"}]
    只输出最相关的前 K 个，K 由用户指定。
    """
    # 结构化 JSON 输入 (segments + query)
    # 单次 LLM 调用 (不分块，受 context window 限制，超长时截断或分段后合并)
    # 4 层降级解析
    # 返回 top_k 结果
```

#### 5.2.3 搜索 UI

**新增 `frontend/src/components/workspace/SemanticSearchBar.vue`:**

- 工作区顶部搜索框 (或快捷键 Cmd/Ctrl+F 唤起)
- 输入自然语言查询 (如「讲性能优化的那段」)
- 结果下拉列表: segment 文本预览 + relevance 分数 + match_reason
- 点击结果跳转到对应 segment + 播放头定位

#### 5.2.4 验收标准

| 验收项 | 标准 |
|--------|------|
| 功能 | 自然语言查询能语义匹配到相关 segment (非仅字面匹配) |
| top_k | 返回结果数 ≤ 用户指定 K |
| 跳转 | 点击结果正确定位播放头 |
| 测试 | 语义匹配逻辑测试 (mock LLM 响应) |

---

## 6. Phase 4d: 集成测试 + 发布

> 预估: 2-3 pd
> 依赖: Phase 4a-4c 全部完成
> 目标: 端到端集成测试、旧代码最终清理、构建验证

### 6.1 集成测试 (1.5 pd)

**当前缺失: 无 `@pytest.mark.integration` 测试，无 TaskManager 全链路测试。**

#### 6.1.1 后端集成测试

**新增 `tests/integration/test_llm_pipeline.py`:**

```python
@pytest.mark.integration
class TestLlmPipelineE2E:
    """End-to-end LLM pipeline tests with mocked LLM responses."""

    def test_p0_smart_delete_full_flow(self, mock_project_service, mock_llm):
        """P0: project -> smart_delete task -> EditDecisions in SuggestionPanel."""
        # 1. 创建项目 + 加载字幕
        # 2. create_task("smart_delete") -> start_task
        # 3. mock LLM 返回删除建议
        # 4. 验证 EditDecision(source="llm_smart") 已添加
        # 5. 验证 active_timeline.edits 包含建议

    def test_p1_subtitle_correction_timestamp_safety(self, ...):
        """P1: 修正后 start/end 物理量不变 (断言层)。"""
        # 1. 加载字幕 (记录原始 start/end)
        # 2. 运行字幕修正
        # 3. 验证每个 segment 的 start/end 与原始完全一致

    def test_multi_timeline_isolation(self, ...):
        """多 Timeline: 在 fork 上操作不影响原始。"""
        # 1. 创建 default timeline
        # 2. fork 出 timeline B
        # 3. 在 B 上运行 P0 删除
        # 4. 验证 default timeline 的 edits 为空，B 有 edits

    def test_p2_highlight_duration_control(self, ...):
        """P2: 精华版时长控制在目标 ±20%。"""
```

**新增 `tests/integration/test_task_manager.py`:**

```python
@pytest.mark.integration
class TestTaskManagerE2E:
    def test_concurrent_timeline_tasks(self, ...):
        """验证多 Timeline 环境下并发任务状态隔离。"""
        # 1. Timeline A 跑 P0, Timeline B 跑 P1
        # 2. 验证结果分别写入正确 timeline
```

#### 6.1.2 前端集成测试

- `TimelineSwitcher` 切换后数据刷新测试
- P1 Review UI 的 accept/reject 流程测试
- P2 精华模式视图切换测试

### 6.2 旧代码最终清理 (0.5 pd)

**清理清单 (4.2.4 已列，此处为最终确认):**

| 文件 | 动作 |
|------|------|
| `core/llm_service.py` | 确认 `_TOPIC_DRIFT_*` 全部删除 |
| `core/models.py` | 确认 `TopicDriftResult` / `TopicDriftData` 删除 |
| `TopicDriftPanel.vue` | 确认删除 |
| `useTopicDrift.ts` | 确认泛化为 `useLlmAnalysis.ts` |
| `main.py` | 确认 `start_topic_drift` / `get_topic_drift_results` / `_handle_topic_drift` 删除 |
| `frontend/src/types/project.ts` | 确认 `TopicDriftResult` / `TopicDriftData` / `Project.topic_drift` 删除 |
| 旧测试文件 | `test_topic_drift.py` 删除或重写为 P0 测试 |

**验证:** `grep -ri "topic_drift\|TopicDrift" core/ main.py frontend/src tests/` 零匹配 (不含文档)。

### 6.2b main.py 模块化拆分 (评估项, 反馈 2.3)

> 反馈指出: `main.py` 已累积 79 个 `@expose` 方法，随着 P0-P3 新增 API 会进一步膨胀。建议考虑分模块加载。

**评估结论: v2.0.0 不做拆分，记录为 v2.1 候选项。**

| 因素 | 分析 |
|------|------|
| 拆分收益 | 单文件从 ~1600 行降至 ~400 行/模块，可读性提升 |
| 拆分成本 | Bridge 的 `@expose` 机制依赖 `MiloCutApi` 单类聚合所有方法，拆分需改造 Bridge 动态绑定逻辑 |
| 风险 | Phase 4d 已是发布前最后阶段，引入架构性改动风险过高 |
| 替代方案 | v2.0.0 内通过 `# region` 注释分区 (project / llm / export / timeline)，保持单文件但提升导航性 |

**v2.0.0 实施约束:** `main.py` 内用注释分区整理现有 79 个 `@expose` 方法，新增 P0-P3/timeline API 放入对应 region。拆分评估文档记录到 `docs/2.0.0/main-refactor-evaluation.md` (可选)。

### 6.3 构建验证 + 发布 (1 pd)

```bash
# 1. 后端测试
uv run pytest --cov=core --cov-report=term-missing

# 2. 前端测试 + 构建
cd frontend && bun run test && bun run build

# 3. Lint
uv run ruff check . && cd frontend && bun run lint

# 4. API 同步检查
uv run python scripts/check_api_sync.py

# 5. 构建 distributable
cd .. && uv run build.py
```

**发布前 checklist:**

- [ ] v1 project.json 迁移测试通过 (至少 3 个真实项目)
- [ ] 多 Timeline 创建/切换/删除/fork 全流程通过
- [ ] P0/P1/P2/P3 各功能端到端可用
- [ ] 时间戳断言层 dev/prod 双模式验证
- [ ] 全量测试零失败
- [ ] Lint 零错误
- [ ] `build.py --onefile` 产物可启动

---

## 7. 技术调研项 (不纳入 v2.0.0 工期)

> 外部审计反馈补充的两个维度。当前代码库无实现，**仅做技术调研**，不阻塞 v2.0.0 发布。结论记录于此供后续版本评估。

### 7.1 LLM 成本与 Token 审计

**反馈指出:** P1 字幕修正和 P2 亮点提取都是全量文本扫描，1 小时视频 (约 1.5 万字) 的 Token 消耗需评估。

**当前基础:**

| 能力 | 当前状态 | 位置 |
|------|----------|------|
| Token 估算 | `estimate_tokens` 启发式 (CJK ~1.5 tok/char) | `core/llm_service.py:32-48` |
| Token 实际用量 | `call_llm` 捕获 OpenAI response 的 `usage` | `core/llm_service.py:138-145` |
| 累计用量 | `analyze_topic_drift` 跨块累计 `total_usage` | `core/llm_service.py:434-468` |
| 成本/$估算 | **无** | -- |
| Cost Estimator | **无** | -- |

**调研方向 (后续版本):**

1. **Cost Estimator 设计:**
   - 预估: 分析前用 `estimate_tokens` 估算总 token，按 provider/model 单价计算预估成本
   - 实际: 分析后用 `call_llm` 返回的 `usage` 计算实际成本
   - UI: 任务启动前显示预估成本，完成后显示实际成本

2. **定价影响:**
   - GPT-4o: ~$2.5/M input, ~$10/M output → 1h 视频 (1.5 万字 ≈ 2.25 万 token) 单次修正约 $0.06-0.25
   - DeepSeek: ~$0.14/M input → 同规模约 $0.003-0.01
   - 本地模型 (Ollama): $0 (仅算力)
   - 结论: 成本差异巨大，Cost Estimator 需按 provider 分别计算

3. **v2.0.0 过渡方案:** P0-P3 完成后，在任务进度面板显示 token 用量 (已有数据)，成本估算延后。

### 7.2 并发与异步任务管理

**反馈指出:** 多 Timeline 环境下，用户可能同时在 Timeline A 跑 P0，Timeline B 跑 P1，需确认并发能力。

**当前状态 (已验证):**

| 能力 | 当前状态 | 位置 |
|------|----------|------|
| 并发执行 | 已支持: `Semaphore(1)` 重任务 + `Semaphore(3)` 轻任务 | `core/task_manager.py:51-52` |
| 优先级队列 | 已支持: `PriorityQueue` + 3 级优先级 | `core/task_manager.py:42, 97` |
| 任务状态隔离 | 已支持: 每个 `MiloTask` 独立，`model_copy` 不可变更新 | `core/models.py:122` |
| 协作取消 | 已支持: 每个运行中任务独立 `threading.Event` | `core/task_manager.py:43` |
| **Timeline 状态隔离** | **未验证** | 多 Timeline 是 Phase 4a 新增，需集成测试验证 |

**调研结论:**

1. `TaskManager` 底层**已具备**并发 + 优先级能力，无需重构。
2. **关键风险:** LLM 任务 (P0/P1/P2/P3) 都是重任务 (`Semaphore(1)`)，**同时只能跑 1 个**。用户在 Timeline A 跑 P0 时，Timeline B 的 P1 会排队等待。这是合理的 (避免 API 限流)，但 UI 需明确提示。
3. **状态隔离需验证:** 多 Timeline 引入后，`_handle_smart_delete` 等 handler 需确保操作的是**发起任务时的 active_timeline_id** (而非实时读取 `active_timeline`，因用户可能在任务排队期间切换了 timeline)。

**v2.0.0 实施约束 (纳入 Phase 4b/4c):**

- 任务 payload **冻结 timeline_id**: `create_task` 时将 `active_timeline_id` 存入 payload
- handler 从 payload 读取 timeline_id，而非 `self._project.active_timeline_id`
- 这解决了「排队期间用户切换 timeline」的状态隔离问题

```python
# main.py _handle_smart_delete
def _handle_smart_delete(self, task: MiloTask, ...):
    # 从 payload 读取，而非实时 active_timeline
    timeline_id = task.payload.get("timeline_id", self._project.active_timeline_id)
    timeline = self._project.get_timeline(timeline_id)
    ...
```

---

## 8. 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 多 Timeline 重构引入回归 | 中 | 高 | L-02 mock 工厂前置 (4a)，`active_timeline` property 机械替换，全量测试 |
| P1 时间戳损坏 | 低 | 极高 | 双层断言 (dev raise / prod warn + 回滚)，专门测试覆盖 |
| P1 LLM 输出长度不匹配 | 中 | 中 | 分层容错 (反馈 2.1): segment_id 最大匹配 + uncovered 标记，不全量失败 |
| P2 拼接音频爆音 | 高 | 低 | 跳变点检测 + crossfade 导出选项 (反馈 2.2) |
| LLM 输出解析失败 | 中 | 中 | 4 层降级解析 (C-02)，跨 provider mock 测试 |
| v1 迁移数据丢失 | 低 | 高 | 迁移测试 (3 个真实项目验证)，迁移失败时保留原文件备份 |
| 任务排队期间 timeline 切换 | 中 | 中 | payload 冻结 timeline_id (7.2) |
| 工期超估 | 中 | 中 | 按阶段验收，4a/4b 可并行部分 (如 P2/P3 与集成测试) 灵活调整 |

---

## 9. 附录

### Appendix A: Phase 4 任务清单 (供 todo 跟踪)

```
Phase 4a (6-7 pd)
  [ ] 4a-1: ruff 引入 + pyproject.toml 配置 + 全量修复 (0.5 pd)
  [ ] 4a-2: ESLint 引入 + eslint.config.js + no-restricted-imports (0.5 pd)
  [ ] 4a-3: 后端 mock 工厂 tests/mocks/factories.py (1.5 pd)
  [ ] 4a-4: 前端 mock 工厂 src/test/helpers/mockProject.ts (0.5 pd, 与 4a-3 合计)
  [ ] 4a-5: API 同步检查脚本 scripts/check_api_sync.py (0.5 pd)
  [ ] 4a-6: Timeline 模型 + Project schema v2 (0.5 pd)
  [ ] 4a-7: v1->v2 迁移逻辑 + 测试 (1 pd)
  [ ] 4a-8: ProjectService active_timeline 适配器 (~49 处替换) (1.5 pd)
  [ ] 4a-9: Timeline CRUD API + main.py expose (0.5 pd)
  [ ] 4a-10: TimelineSwitcher UI + WorkspacePage 适配 (1 pd)

Phase 4b (5-7 pd)
  [ ] 4b-1: C-02 输入结构化 _build_structured_user_message (0.5 pd)
  [ ] 4b-2: C-02 输出 4 层降级 _parse_json_response_layers (0.5 pd)
  [ ] 4b-3: C-02 provider response_format 适配 (0.5 pd, 可选)
  [ ] 4b-4: P0 chunk_transcript_short + analyze_smart_delete (1 pd)
  [ ] 4b-5: P0 集成 EditDecision(source="llm_smart") + main.py handler (0.5 pd)
  [ ] 4b-6: P0 增量分析 (跳过规则已标记) (0.5 pd)
  [ ] 4b-7: P1 analyze_subtitle_correction (模式 A/B + context_window) (1 pd)
  [ ] 4b-8: P1 word-level diff 对齐 (difflib) (1 pd)
  [ ] 4b-9: P1 时间戳双层断言 + 分层容错 1:1 约束 + 字符级置信度 (0.5 pd)
  [ ] 4b-10: P1 SubtitleCorrectionReview.vue + 批量信任功能 (1 pd)
  [ ] 4b-11: Topic Drift 旧代码清理 (0.5 pd)

Phase 4c (5-6 pd)
  [ ] 4c-1: P2 analyze_highlights + 时长裁剪算法 (1.5 pd)
  [ ] 4c-2: P2 HighlightModeView.vue + 跳变点提示 (1.5 pd)
  [ ] 4c-3: P2 导出精华版 + 跳变点 crossfade 处理 (0.5 pd, 复用现有导出)
  [ ] 4c-4: P3 semantic_search + top_k (1 pd)
  [ ] 4c-5: P3 SemanticSearchBar.vue + 跳转 (1 pd)

Phase 4d (2-3 pd)
  [ ] 4d-1: 后端集成测试 (LLM pipeline E2E + 多 timeline 隔离) (1 pd)
  [ ] 4d-2: 前端集成测试 (切换器 + Review UI + 精华模式) (0.5 pd)
  [ ] 4d-3: 旧代码最终清理确认 + main.py region 分区 (0.5 pd)
  [ ] 4d-4: 构建验证 + 发布 checklist (1 pd)
```

### Appendix B: 反馈采纳对照

| 反馈建议 | 采纳状态 | 实施位置 |
|----------|----------|----------|
| 工程化前置 (先 L-01/L-02 再重构) | **采纳** | Phase 4a 前半 (3.1-3.3) |
| 多 Timeline 估算偏乐观预警 | **采纳** | 3.4.1 风险评估，引入 active_timeline 适配器降低风险 |
| ProjectService 适配器模式 | **采纳** | 3.4.4 `active_timeline` property + `_update_active_timeline` |
| C-02 输入结构化 JSON | **采纳** | 4.1.1 `_build_structured_user_message` |
| P1 context_window (前后 2-3 segment) | **采纳** | 4.3.1 `context_window` 参数 |
| P1 时间戳断言层 | **采纳 (双层)** | 4.3.2 dev raise / prod warn + 回滚 |
| P1 1:1 约束容错 (部分匹配+uncovered标记) | **采纳** | 4.3.2 分层容错策略，不全量失败 |
| P2 跳变点/crossfade 处理 | **采纳** | 5.1.4 `_detect_jump_cuts` + 导出选项 crossfade/smart/none |
| 用户心智负担 (信任此来源批量确认) | **采纳** | 4.2.5 + 4.3.3 SuggestionPanel/Review UI 新增「Accept all from source」 |
| main.py 模块化拆分 | **评估后缓做** | 6.2b v2.0.0 内仅 region 分区，拆分记录为 v2.1 候选 |
| LLM 成本审计 (Cost Estimator) | **技术调研** | 7.1 (不纳入 v2.0.0 工期) |
| 并发任务管理 | **技术调研 + 实施约束** | 7.2 (payload 冻结 timeline_id 纳入 4b/4c) |
| 即使不引入完整 ESLint 也强制 vue-tsc 严格模式 | **已满足** | 当前 tsconfig.json 已 `"strict": true` (1.3)，4a 补充 ruff |
| Phase 4 前补齐 L-01/L-02 避免 test 雪崩 | **采纳** | 4a 顺序: L-01 → L-02 → 多 Timeline |

### Appendix C: 决策记录

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| D-01 | 工程化是否前置 | 前置 (L-01/L-02/L-03 作为 4a 前半) | 大规模重构前需测试套件稳定，避免雪崩 |
| D-02 | 成本/并发审计项 | 仅技术调研，不纳入 v2.0.0 | 聚焦核心功能交付，成本估算延后 |
| D-03 | P1 时间戳断言 | 双层 (dev raise / prod warn) | 开发期强保证发现问题，生产期容错不中断 |
| D-04 | Topic Drift 旧代码 | 全部删除，不保留 | 方向 E 确认重构，保留增加维护负担 |
| D-05 | 多 Timeline 数据模型 | 每 timeline 独立 transcript (非 overlay 叠加) | segment ID 体系自洽，P1 断句修正时 edits 引用始终有效 |
| D-06 | P3 搜索方式 | LLM 语义匹配 (非 embedding 向量) | 避免引入向量数据库依赖，保持架构简洁 |
| D-07 | P1 1:1 约束策略 | 分层容错 (非严格报错) | 长视频 LLM 输出可能不匹配，全量失败体验差；部分匹配+uncovered标记更实用 |
| D-08 | P2 跳变点处理 | 检测+可选 crossfade 导出 | 直接拼接远距离 highlight 会产生音频爆音 |
| D-09 | 批量确认交互 | 「信任此来源」一键 accept 高置信度 | 降低用户逐条确认的心智负担 |
| D-10 | main.py 拆分 | v2.0.0 不拆分，region 分区替代 | 发布前避免架构性改动，拆分延后 v2.1 |

---

## 10. 批准与启动

**批准条件:**

1. 本计划经 review 确认
2. Phase 4a 启动前确认 L-01/L-02 优先级 (不跳过)
3. 确认 v1 迁移测试覆盖至少 3 个真实项目

**启动标志:** Phase 4a-1 (ruff 引入) 开始执行。

---

> **文档版本:** 1.0
> **创建日期:** 2026-06-14
> **基于:** `audit-report-v2.0.0-2.md` (Appendix B 当前实现状态快照) + 外部审计反馈
> **下一步:** 待批准后从 Phase 4a-1 启动
