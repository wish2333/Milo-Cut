#!/usr/bin/env bash
# scripts/gates-v3.0.5.sh -- v3.0.5 phase 门禁三段封装
#
# 依据: docs/3.0.5/plan-v3.0.5.md P0-2 / spec-v3.0.5.md M-gate 门禁命令块
# 约定:
#   - 命令与期望输出原样取自 SPEC M-gate, 零改写; 仅加段落标题与汇总 exit code
#   - 门禁 diff 基准恒为 tag v3.0.4 (不受文档入库与 tag v3.0.5-base 影响)
#   - 每 phase 合入前执行一次, stdout 全文贴当步 record
#   - SPEC 与本脚本冲突时以 SPEC 为准, 当场修脚本
#   - shell 环境受限时回落命令块手动执行 + record 登记 (不得因脚本问题阻塞合入)
# 用法:
#   bash scripts/gates-v3.0.5.sh            # 三段全跑
#   bash scripts/gates-v3.0.5.sh backend    # 仅后端段
#   bash scripts/gates-v3.0.5.sh frontend   # 仅前端段
#   bash scripts/gates-v3.0.5.sh redline    # 仅红线段
#
# 执行环境注记 (record-3.0.4-P0-1.md 先例, 本版沿用):
#   本沙箱环境 bun run 不可用 (CouldntReadCurrentDirectory), 脚本自动探测:
#   bun run 可用则用 bun run test/build/lint, 否则回落 node_modules/.bin 等价命令。

set -u
cd "$(dirname "$0")/.."

BASELINE="v3.0.4"
FAIL=0
SEG="${1:-all}"

ok()   { echo "  [PASS] $1"; }
bad()  { echo "  [FAIL] $1"; FAIL=1; }
info() { echo "  [INFO] $1"; }

# ---------------------------------------------------------------
# 段一: 后端门禁
# ---------------------------------------------------------------
gates_backend() {
  echo ""
  echo "===== 后端门禁 ====="
  echo "--- uv run pytest  (期望: >=833 只增不减全绿; 当期期望总数见 record 登记表) ---"
  if uv run pytest; then ok "pytest 全绿"; else bad "pytest 存在失败"; fi

  echo "--- uv run ruff check .  (期望: 0 problems) ---"
  if uv run ruff check .; then ok "ruff 0 problems"; else bad "ruff 有问题"; fi
}

# ---------------------------------------------------------------
# 段二: 前端门禁 (bun run 不可用时回落 node 等价命令, 等价性登记于 record)
# ---------------------------------------------------------------
BUN_RUN_OK=0
if command -v bun >/dev/null 2>&1; then
  if bun run --version >/dev/null 2>&1; then BUN_RUN_OK=1; fi
fi

vitest_assert() {
  # $1 = vitest 输出文件; 判定: exit 0 全绿 (R5.16 根修后口径), 或唯一失败 = useRowLayout.perf.test.ts
  local out="$1" rc="$2"
  if [ "$rc" -eq 0 ]; then ok "vitest 全绿 (collected 见上方统计)"; return; fi
  local counts failed passed collected
  counts=$(grep -E "Tests[[:space:]]+[0-9]+ failed" "$out" | tail -1 | grep -oE "[0-9]+ failed \| [0-9]+ passed \([0-9]+\)" | tail -1)
  if [ -z "$counts" ]; then bad "vitest 失败且无法解析统计行, 人工核对"; return; fi
  failed=$(echo "$counts" | grep -oE "^[0-9]+")
  passed=$(echo "$counts" | sed -E 's/^[0-9]+ failed \| ([0-9]+) passed.*/\1/')
  collected=$(echo "$counts" | grep -oE "\([0-9]+\)" | tr -d '()')
  if [ "$failed" -eq 1 ] && [ "$passed" -eq "$((collected - 1))" ] \
     && grep -q "useRowLayout.perf.test.ts" "$out" \
     && [ "$(grep -c "FAIL" "$out")" -le 1 ]; then
    ok "vitest 唯一失败 = useRowLayout.perf.test.ts (已登记环境例) ${passed}/${collected}"
  else
    bad "vitest 失败数或失败项不符合登记口径 (failed=${failed} passed=${passed} collected=${collected})"
  fi
}

gates_frontend() {
  echo ""
  echo "===== 前端门禁 ====="
  local out rc
  out=$(mktemp)
  if [ "$BUN_RUN_OK" -eq 1 ]; then
    echo "--- cd frontend && bun run test  (期望: passed = collected - 1, 唯一失败 = useRowLayout.perf.test.ts; R5.16 根修后期望全绿) ---"
    ( cd frontend && bun run test ) >"$out" 2>&1; rc=$?
  else
    echo "--- [回落] frontend vitest run  (bun run 不可用, node 等价命令, 已登记) ---"
    ( cd frontend && ./node_modules/.bin/vitest run ) >"$out" 2>&1; rc=$?
  fi
  tail -6 "$out"
  vitest_assert "$out" "$rc"

  if [ "$BUN_RUN_OK" -eq 1 ]; then
    echo "--- cd frontend && bun run build  (期望: vue-tsc --noEmit + vite build 通过) ---"
    if ( cd frontend && bun run build ); then ok "build 通过"; else bad "build 失败"; fi
    echo "--- cd frontend && bun run lint  (期望: 0 errors 0 warnings) ---"
    if ( cd frontend && bun run lint ); then ok "lint 0/0"; else bad "lint 有告警"; fi
  else
    echo "--- [回落] frontend vue-tsc --noEmit + vite build ---"
    if ( cd frontend && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build >/dev/null ); then ok "build 通过"; else bad "build 失败"; fi
    echo "--- [回落] frontend eslint . ---"
    if ( cd frontend && ./node_modules/.bin/eslint . ); then ok "lint 0/0"; else bad "lint 有告警"; fi
  fi
  rm -f "$out"
}

# ---------------------------------------------------------------
# 段三: 红线检查 (R0-1 ~ R0-5, 基准 = v3.0.4)
# ---------------------------------------------------------------
gates_redline() {
  echo ""
  echo "===== 红线检查 (基准 = ${BASELINE}) ====="
  local tmp
  tmp=$(mktemp)

  echo "--- R0-1 后端 diff 白名单: git diff ${BASELINE} --name-only -- core/ main.py (输出必须 ⊆ SPEC M0 白名单表) ---"
  git diff "${BASELINE}" --name-only -- core/ main.py >"$tmp" || true
  if [ ! -s "$tmp" ]; then
    ok "后端 diff 为空"
  else
    local wl=0
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      case "$f" in
        core/llm_service.py|core/correction_service.py|core/project_service.py|core/llm_prompts.py|core/config.py|main.py)
          info "白名单内: $f (逐 hunk 对应 R5.x 编号, 见登记表)" ;;
        *) bad "白名单外后端 diff: $f"; wl=1 ;;
      esac
    done <"$tmp"
    [ "$wl" -eq 0 ] && ok "后端 diff 文件集全部在白名单内 (登记表核对责任在执行者)"
  fi

  echo "--- R0-1 禁改面 diff 必须为空: pywebvue/ core/models.py core/events.py core/task_manager.py core/export_service.py core/export_timeline.py core/track_constraints.py core/workflow_engine.py core/ffmpeg_service.py core/ffmpeg_presets.py core/subtitle_service.py core/timeline_utils.py core/diff_service.py core/migrations.py ---"
  git diff "${BASELINE}" --name-only -- pywebvue/ core/models.py core/events.py core/task_manager.py \
    core/export_service.py core/export_timeline.py core/track_constraints.py core/workflow_engine.py \
    core/ffmpeg_service.py core/ffmpeg_presets.py core/subtitle_service.py \
    core/timeline_utils.py core/diff_service.py core/migrations.py >"$tmp" || true
  if [ ! -s "$tmp" ]; then ok "禁改面为空"; else bad "禁改面出现改动:"; cat "$tmp"; fi

  echo "--- R0-2 events 双侧同步 (v3.0.5 无新增事件, 期望双侧均 0 行) ---"
  local n_py n_ts
  n_py=$(git diff "${BASELINE}" -- core/events.py | wc -l)
  n_ts=$(git diff "${BASELINE}" -- frontend/src/utils/events.ts | wc -l)
  echo "  events.py diff 行数 ${n_py} / events.ts diff 行数 ${n_ts}"
  if [ "$n_py" -eq 0 ] && [ "$n_ts" -eq 0 ]; then
    ok "R0-2 events 双侧零改动 (符合本版无新增事件口径)"
  else
    bad "R0-2 events 出现改动 (py=${n_py} ts=${n_ts}; 本版白名单不含 events, 若确有需求须先修 SPEC/脚本)"
  fi

  echo "--- R0-3 后端断言零删改 (期望 = 0; 反转白名单文件 = tests/test_llm_translation.py, 行粒度 :217/:614 由 diff 审查制人工核对): git diff ${BASELINE} -- tests/ ---"
  local n_a; n_a=$(git diff "${BASELINE}" -- tests/ | awk '
    /^\+\+\+ b\// { f = $2 }
    /^-[[:space:]]*(assert |self\.assert)/ && f !~ /test_llm_translation\.py$/ { c++ }
    END { print c + 0 }')
  echo "  白名单外后端断言删除行数 = ${n_a}"
  [ "$n_a" -eq 0 ] && ok "后端断言白名单外零删改" || bad "白名单外断言删改命中"

  echo "--- R0-3 前端断言白名单外零删改 (期望 = 0; 反转白名单文件 = AIAssistantPanel.test.ts / SegmentBlocksLayer.test.ts, 行粒度由 diff 审查制人工核对) ---"
  local n_e; n_e=$(git diff "${BASELINE}" -- frontend/src | awk '
    /^\+\+\+ b\// { f = $2 }
    /^-[[:space:]]*expect\(/ && f !~ /AIAssistantPanel\.test\.ts$/ && f !~ /SegmentBlocksLayer\.test\.ts$/ { c++ }
    END { print c + 0 }')
  echo "  白名单外 expect 删除行数 = ${n_e}"
  [ "$n_e" -eq 0 ] && ok "前端断言白名单外零删改" || bad "白名单外断言删改命中"

  echo "--- R0-4 专项: git diff ${BASELINE} -- core/config.py core/llm_prompts.py (期望: config 仅 DEFAULTS 追加质量模式键 1 行; llm_prompts 仅 aligned_main_text 语义说明受控增行; diff 审查制人工核对) ---"
  git diff "${BASELINE}" -- core/config.py core/llm_prompts.py
  info "config/llm_prompts diff 如上, 逐行人工核对 (只增)"

  echo "--- R0-5 diff 审查制: git diff ${BASELINE} --stat -- core/ main.py (逐条对照后端改动登记表) ---"
  git diff "${BASELINE}" --stat -- core/ main.py
  echo "--- R0-5 人工核对 (SPEC 遗漏注记先例): 全量 name-only 无 dev.py / build.py ---"
  git diff "${BASELINE}" --name-only | grep -E '^(dev|build)\.py$' >"$tmp" || true
  if [ ! -s "$tmp" ]; then ok "dev.py / build.py 零改动"; else bad "禁改文件被改:"; cat "$tmp"; fi

  rm -f "$tmp"
}

case "$SEG" in
  backend)  gates_backend ;;
  frontend) gates_frontend ;;
  redline)  gates_redline ;;
  all)      gates_backend; gates_frontend; gates_redline ;;
  *) echo "用法: bash scripts/gates-v3.0.5.sh [all|backend|frontend|redline]"; exit 2 ;;
esac

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "===== 门禁汇总: 全部通过 (exit 0) ====="
  exit 0
else
  echo "===== 门禁汇总: 存在失败项 (exit 1) -- 阻塞合入, 不放宽标准 ====="
  exit 1
fi
