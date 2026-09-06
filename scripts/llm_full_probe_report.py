"""Full LLM probe with report generation.

Runs all 5 LLM features against the Pandora project, then writes a
human-readable analysis report (UTF-8 markdown) for review.

Usage:  uv run scripts/llm_full_probe.py
Output: scripts/llm_full_report.md
"""

# ruff: noqa: E402  -- script bootstrap: sys.path before imports

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm_prompts import (
    _HIGHLIGHT_SYSTEM,
    _SEARCH_SYSTEM,
    _SMART_DELETE_SYSTEM,
    _SUBTITLE_CORRECTION_SYSTEM_A,
    _SUBTITLE_CORRECTION_SYSTEM_B,
)
from core.llm_service import (
    analyze_highlights,
    analyze_smart_delete,
    analyze_subtitle_correction,
    get_llm_config,
    semantic_search,
    test_connection,
)

REPORT = ROOT / "scripts" / "llm_full_report.md"
RAW = ROOT / "scripts" / "llm_full_raw.json"


def load_pandora_segments() -> list[dict]:
    proj_path = ROOT / "data" / "projects" / "20260514-潘多拉之心第二卷卷评" / "project.json"
    data = json.loads(proj_path.read_text(encoding="utf-8"))
    timelines = data.get("timelines", [])
    for tl in timelines:
        if tl.get("id") == data.get("active_timeline_id", "default"):
            segs = tl.get("transcript", {}).get("segments", [])
            return [s for s in segs if s.get("text", "").strip()]
    for tl in timelines:
        segs = tl.get("transcript", {}).get("segments", [])
        if segs:
            return [s for s in segs if s.get("text", "").strip()]
    return []


def run_probe() -> dict:
    """Run all probes, return structured results."""
    cfg = get_llm_config()
    segments = load_pandora_segments()
    seg_map = {s["id"]: s for s in segments}
    subset = segments[:20]

    results: dict = {
        "config": {
            "provider": str(cfg.provider),
            "base_url": cfg.resolved_base_url(),
            "model": cfg.resolved_model(),
            "temperature": cfg.temperature,
            "timeout": cfg.timeout,
        },
        "segment_count": len(segments),
        "subset_count": len(subset),
    }

    # --- test_connection ---
    t0 = time.monotonic()
    res = test_connection()
    results["test_connection"] = {
        "wall_time_ms": (time.monotonic() - t0) * 1000,
        "success": res.get("success"),
        "data": res.get("data"),
        "error": res.get("error"),
    }

    # --- smart_delete (20 segments) ---
    t0 = time.monotonic()
    res = analyze_smart_delete(subset)
    dt = time.monotonic() - t0
    sd_raw = res.get("data", {}).get("results", []) if res.get("success") else []
    results["smart_delete"] = {
        "wall_time_s": dt,
        "success": res.get("success"),
        "error": res.get("error"),
        "count": len(sd_raw),
        "token_usage": res.get("data", {}).get("token_usage", {}),
        "results": [
            {**r, "text": seg_map.get(r["segment_id"], {}).get("text", "??")}
            for r in sd_raw
        ],
    }

    # --- subtitle_correction mode A (20 segments) ---
    t0 = time.monotonic()
    res = analyze_subtitle_correction(subset)
    dt = time.monotonic() - t0
    sc_raw = res.get("data", {}).get("corrections", []) if res.get("success") else []
    results["subtitle_correction"] = {
        "wall_time_s": dt,
        "success": res.get("success"),
        "error": res.get("error"),
        "count": len(sc_raw),
        "token_usage": res.get("data", {}).get("token_usage", {}),
        "results": [
            {**c, "original_text": seg_map.get(c["segment_id"], {}).get("text", "??")}
            for c in sc_raw
        ],
    }

    # --- highlights (full transcript) ---
    t0 = time.monotonic()
    res = analyze_highlights(segments, target_duration_minutes=10)
    dt = time.monotonic() - t0
    hl_raw = res.get("data", {}).get("results", []) if res.get("success") else []
    results["highlights"] = {
        "wall_time_s": dt,
        "success": res.get("success"),
        "error": res.get("error"),
        "count": len(hl_raw),
        "total_duration": res.get("data", {}).get("total_highlight_duration"),
        "token_usage": res.get("data", {}).get("token_usage", {}),
        "results": [
            {**r, "text": seg_map.get(r["segment_id"], {}).get("text", "??")}
            for r in hl_raw
        ],
    }

    # --- semantic_search ---
    t0 = time.monotonic()
    res = semantic_search("主角的成长", segments, top_k=5)
    dt = time.monotonic() - t0
    ss_raw = res.get("data", {}).get("results", []) if res.get("success") else []
    results["semantic_search"] = {
        "wall_time_s": dt,
        "success": res.get("success"),
        "error": res.get("error"),
        "count": len(ss_raw),
        "token_usage": res.get("data", {}).get("token_usage", {}),
        "results": [
            {**r, "text": seg_map.get(r["segment_id"], {}).get("text", "??")}
            for r in ss_raw
        ],
    }

    return results


def generate_report(r: dict) -> str:
    """Generate human-readable markdown report from probe results."""
    lines: list[str] = []
    w = lines.append

    w("# LLM 全功能探针报告")
    w(f"\n> 项目: 20260514-潘多拉之心第二卷卷评 | 模型: {r['config']['model']} | 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    w("")

    # -- Config --
    w("## 1. 配置信息")
    w("")
    w("| 项目 | 值 |")
    w("|------|------|")
    for k, v in r["config"].items():
        w(f"| {k} | `{v}` |")
    w(f"| 总片段数 | {r['segment_count']} |")
    w(f"| 测试子集 | 前 {r['subset_count']} 段 (smart_delete/subtitle_correction) + 全量 (highlight/search) |")
    w("")

    # -- test_connection --
    w("## 2. 连接测试 (test_connection)")
    w("")
    tc = r["test_connection"]
    status = "PASS" if tc["success"] else "FAIL"
    w(f"- **状态**: {status}")
    w(f"- **耗时**: {tc['wall_time_ms']:.0f}ms")
    if tc["success"]:
        d = tc["data"]
        w(f"- **模型**: {d.get('model')}")
        w(f"- **响应时间**: {d.get('response_time_ms')}ms")
    else:
        w(f"- **错误**: {tc['error']}")
    w("")

    # -- smart_delete --
    w("## 3. 智能删除 (smart_delete)")
    w("")
    _print_feature_section(w, r["smart_delete"], "smart_delete")
    # Analysis
    sd = r["smart_delete"]
    if sd["success"] and sd["results"]:
        w("### 分析")
        w("")
        cats: dict[str, int] = {}
        for item in sd["results"]:
            cats[item["category"]] = cats.get(item["category"], 0) + 1
        w(f"- 删除建议分布: {cats}")
        # Check: 重复片段是否只保留最后一版
        dup_ids = [i for i in sd["results"] if i["category"] == "semantic_dup"]
        if dup_ids:
            w(f"- semantic_dup 数量: {len(dup_ids)} (这些应是被保留的最后一版之前的重复片段)")
        w("")

    # -- subtitle_correction --
    w("## 4. 字幕修正 (subtitle_correction mode A)")
    w("")
    _print_feature_section(w, r["subtitle_correction"], "subtitle_correction")
    sc = r["subtitle_correction"]
    if sc["success"] and sc["results"]:
        w("### 分析")
        w("")
        # Check punctuation rules
        has_trailing_punct = 0
        has_mid_punct = 0
        for item in sc["results"]:
            ct = item["corrected_text"]
            if ct and ct[-1] in "。，？！；、,.!?;":
                has_trailing_punct += 1
            import re
            if re.search(r"[。，？！；、,.!?;]", ct[:-1] if len(ct) > 1 else ""):
                has_mid_punct += 1
        w(f"- 标点检查: 句尾残留标点 {has_trailing_punct} 个, 句中残留标点 {has_mid_punct} 个 (均应为 0)")
        w("")

    # -- highlights --
    w("## 5. 精华提取 (highlights)")
    w("")
    _print_feature_section(w, r["highlights"], "highlights")
    hl = r["highlights"]
    if hl["success"] and hl["results"]:
        w("### 分析")
        w("")
        densities: dict[str, int] = {}
        for item in hl["results"]:
            densities[item["density"]] = densities.get(item["density"], 0) + 1
        w(f"- 密度分布: {densities}")
        w(f"- 总时长: {hl.get('total_duration', 0):.1f}s / 600s 目标")
        w("")

    # -- semantic_search --
    w("## 6. 语义搜索 (semantic_search)")
    w("")
    _print_feature_section(w, r["semantic_search"], "semantic_search")
    w("")

    # -- Prompt appendix --
    w("## 附录: 当前生效的提示词")
    w("")
    prompts = [
        ("smart_delete", _SMART_DELETE_SYSTEM),
        ("subtitle_correction_a", _SUBTITLE_CORRECTION_SYSTEM_A),
        ("subtitle_correction_b", _SUBTITLE_CORRECTION_SYSTEM_B),
        ("highlight", _HIGHLIGHT_SYSTEM),
        ("search", _SEARCH_SYSTEM),
    ]
    for key, text in prompts:
        w(f"### {key}")
        w("```")
        w(text.strip())
        w("```")
        w("")

    return "\n".join(lines)


def _print_feature_section(w, data: dict, name: str) -> None:
    """Print a standard feature result section."""
    if not data["success"]:
        w("- **状态**: FAIL")
        w(f"- **错误**: {data.get('error')}")
        w("")
        return

    w("- **状态**: PASS")
    w(f"- **耗时**: {data['wall_time_s']:.1f}s")
    w(f"- **结果数**: {data['count']}")
    tu = data.get("token_usage", {})
    if tu:
        w(f"- **Token**: prompt={tu.get('prompt_tokens', 0)}, completion={tu.get('completion_tokens', 0)}, total={tu.get('total_tokens', 0)}")
    w("")

    if data["results"]:
        w("| segment_id | 原文 | 结果 |")
        w("|------------|------|------|")
        for item in data["results"]:
            sid = item["segment_id"]
            orig = item.get("original_text", item.get("text", ""))
            if name == "smart_delete":
                w(f"| {sid} | {orig} | delete [{item['category']}] conf={item.get('confidence', '?')} -- {item.get('reason', '')} |")
            elif name == "subtitle_correction":
                w(f"| {sid} | {orig} | -> {item['corrected_text']} [{item['category']}] -- {item.get('changes', [])} |")
            elif name == "highlights":
                w(f"| {sid} | {orig} | {item['density']} -- {item.get('highlight_reason', '')} |")
            elif name == "semantic_search":
                w(f"| {sid} | {orig} | rel={item['relevance']} -- {item.get('match_reason', '')} |")
        w("")


def main() -> None:
    print("Running full LLM probe...")
    results = run_probe()

    # Save raw JSON
    RAW.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw JSON saved to {RAW}")

    # Generate markdown report
    report = generate_report(results)
    REPORT.write_text(report, encoding="utf-8")
    print(f"Report saved to {REPORT}")
    print(f"\nDone. Open {REPORT.name} to review.")


if __name__ == "__main__":
    main()
