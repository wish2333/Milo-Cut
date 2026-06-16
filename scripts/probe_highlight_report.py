"""Save full highlight probe results to a markdown report file."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm_service import analyze_highlights


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


def main() -> None:
    segments = load_pandora_segments()
    seg_map = {s["id"]: s for s in segments}

    t0 = time.monotonic()
    res = analyze_highlights(segments, target_duration_minutes=10)
    dt = time.monotonic() - t0

    lines: list[str] = []
    w = lines.append

    w("# 精华提取 (highlight) 上下文连贯性探针报告")
    w(f"\n> 模型: glm-5-turbo | 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    w(f"> chunk: 30 分钟 (单次调用) | 超时: max(config, 300)s")
    w("")

    if not res.get("success"):
        w(f"**ERROR**: {res.get('error')}")
        Path(ROOT / "scripts" / "highlight_report.md").write_text("\n".join(lines), encoding="utf-8")
        return

    results = res["data"]["results"]
    tu = res["data"].get("token_usage", {})

    w("## 概要")
    w("")
    w(f"| 指标 | 值 |")
    w(f"|------|------|")
    w(f"| 总片段数 | {len(segments)} |")
    w(f"| 选中片段数 | {len(results)} |")
    w(f"| 耗时 | {dt:.1f}s |")
    w(f"| Token | prompt={tu.get('prompt_tokens',0)}, completion={tu.get('completion_tokens',0)}, total={tu.get('total_tokens',0)} |")
    w(f"| 总高光时长 | {res['data'].get('total_highlight_duration',0):.1f}s / 600s 目标 |")

    densities: dict[str, int] = {}
    for r in results:
        densities[r["density"]] = densities.get(r["density"], 0) + 1
    w(f"| 密度分布 | {densities} |")
    w("")

    # Gap analysis
    w("## 上下文连贯性分析")
    w("")
    gaps: list[tuple[str, float]] = []
    prev_end = 0.0
    for r in results:
        seg = seg_map.get(r["segment_id"], {})
        gap = seg.get("start", 0) - prev_end
        if gap > 5:
            gaps.append((r["segment_id"], gap))
        prev_end = seg.get("end", 0)
    w(f"- 大跳转 (gap>5s) 次数: {len(gaps)}")
    if gaps:
        w(f"- 跳转详情: {[(sid, f'{g:.0f}s') for sid, g in gaps]}")
    else:
        w(f"- 无大跳转，片段连续性好")
    w("")

    # Full results table
    w("## 逐条结果")
    w("")
    w("| segment_id | 时间 | gap | 密度 | 文本 | 理由 |")
    w("|------------|------|-----|------|------|------|")
    prev_end = 0.0
    for r in results:
        seg = seg_map.get(r["segment_id"], {})
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        gap = start - prev_end
        gap_str = f"**{gap:.0f}s**" if gap > 5 else f"{gap:.0f}s" if gap > 0 else "-"
        text = seg.get("text", "??")
        reason = r.get("highlight_reason", "")
        w(f"| {r['segment_id']} | {start:.0f}-{end:.0f}s | {gap_str} | {r['density']} | {text} | {reason} |")
        prev_end = end
    w("")

    report_path = ROOT / "scripts" / "highlight_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
