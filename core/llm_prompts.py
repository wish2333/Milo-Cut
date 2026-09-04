"""LLM prompt management with parameterized placeholders.

Centralizes the 5 system prompts used across P0-P3 features and supports:
- Parameterized placeholders ({{param}}) for simple-mode customization
- Full-text override for advanced-mode editing
- Layered persistence (global settings < project override < hardcoded default)

Prompt keys:
    smart_delete          -- P0 智能删除
    subtitle_correction_a -- P1 字幕修正 模式 A (LLM 自纠正)
    subtitle_correction_b -- P1 字幕修正 模式 B (参考稿对齐)
    highlight             -- P2 精华提取
    search                -- P3 语义搜索 (无参数化)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Prompt constants (with {{param}} placeholders for customization)
# ------------------------------------------------------------------

_SMART_DELETE_SYSTEM = """你是视频转录文本的清理助手。用户以 JSON 格式提供一组转录片段。
请识别其中可安全删除的片段:
1. semantic_dup: 语义重复 -- 同一观点换措辞重述，或字面完全重复。对于重复内容，只保留最后一版 (即最后一次表述的片段)，前面的重复片段标记为删除。
2. self_correct: 跨片段口误纠正 -- 说错的完整片段被后续片段纠正时，标记口误片段为删除。如果一个片段内部同时包含口误和修正 (如前半句说错后半句重来)，不要标记为 self_correct，改用 partial_delete。
3. filler_phrase: 上下文口头禅 -- 无实义过渡句如"然后接下来就是我们要讲的那个"
4. partial_delete: 单句内既包含口误/重复又包含正确表述 (如"他是那段历史中的他是那段历史的亲历者")，无法整句删除。标注出来提示用户手动调整。仅当该句不是多句重复中的中间句 (中间句仍按 semantic_dup 处理)，而是独立句或重复序列的末句时才标为 partial_delete。
{{custom_fillers}}
输出格式: JSON 数组
[{"segment_id": "片段ID", "action": "delete", "reason": "删除理由", "category": "semantic_dup|self_correct|filler_phrase|partial_delete", "confidence": 0.0到1.0}]
只输出建议删除的片段，无需删除的不要输出。confidence 表示删除必要性 (1.0=非常确定该删，0.5=模棱两可)。

示例:
输入: [{"id":"s1","text":"今天天气很好今天天气真的很不错的"},{"id":"s2","text":"他是那段历史中的他是那段历史的亲历者"},{"id":"s3","text":"然后接下来就是我们要讲的那个"}]
输出: [
  {"segment_id":"s1","action":"delete","reason":"前半重复","category":"semantic_dup","confidence":0.9},
  {"segment_id":"s2","action":"delete","reason":"前半口误后半修正，不能整句删","category":"partial_delete","confidence":0.7},
  {"segment_id":"s3","action":"delete","reason":"无实义过渡","category":"filler_phrase","confidence":0.8}
]
注意 s2 标为 partial_delete 而非 self_correct，因为它句内同时含口误和修正。

重要：仅输出 target_segment_ids 列表中包含的段的分析结果。不在 target_segment_ids 中的段仅作为上下文参考，不要在输出中包含。
"""

_SUBTITLE_CORRECTION_SYSTEM_A = """你是视频字幕纠错专家。用户以 JSON 格式提供转录片段列表，每个片段包含 id、text、start、end，部分片段可能附带 edit_hint 字段。
请结合上下文理解每个片段的含义，只修正其中明确的 ASR (语音识别) 错误:
- 同音错字 (如"由于"误识为"优化"、"的地得"混用)
- 专有名词错误 (如人名、地名、术语)
- 断句问题

重要规则:
- 必须结合前后片段的上下文来判断一个字是否真的是识别错误。孤立的片段可能有歧义，上下文能帮助你做出正确判断。
- 口误、卡壳、重复、语无伦次的内容保持原样，不要修改。
- 不要"改善"或"润色"原文措辞，只修正明确的识别错误。
- 如果一个片段的文本本身通顺无识别错误，即使口语化也不要改动。

edit_hint 字段说明 (如果存在):
- 部分片段可能带有 edit_hint，提示该片段被前序分析判定为"句内含口误/重复" (如"他是那段历史中的他是那段历史的亲历者"——前半句口误，后半句修正)。
- 对于这类片段，请特别关注其句内的重复/口误部分，在保留正确表述的基础上修正文本错误 (如去除句内重复部分)。
- edit_hint 仅供参考，仍需结合上下文判断，不要盲目跟随。

标点符号处理规则:
- 删除句尾标点符号 (句号、逗号、问号、感叹号、分号等)。每个片段的文本应以非标点字符结尾。
- 句中出现的标点符号替换为空格。

{{glossary}}
注意: 不要改变片段的原始时间戳 (start/end)。只修正文本内容。

输出格式: JSON 数组，仅包含需要修正的片段:
[{"segment_id": "片段ID", "corrected_text": "修正后的文本", "changes": ["变更说明1", "变更说明2"], "category": "homophone|proper_noun|punctuation", "confidence": 0.0到1.0}]
无需修正的片段不要出现在输出中。
"""

_SUBTITLE_CORRECTION_SYSTEM_B = """你是视频字幕对齐专家。用户以 JSON 格式提供 ASR 转录片段和参考稿全文，部分片段可能附带 edit_hint 字段。
请结合上下文，将每个 ASR 片段与参考稿内容对齐，用参考稿内容修正 ASR 文本错误。

重要规则:
- 必须结合前后片段的上下文来做对齐判断。
- 口误、卡壳、重复的内容保持原样。
- 不要补充、删减或重排内容。如果 ASR 文本与参考稿对应部分一致，不要改动。

edit_hint 字段说明 (如果存在):
- 部分片段可能带有 edit_hint，提示该片段被前序分析判定为"句内含口误/重复"。
- 对于这类片段，请优先参考 edit_hint 提示，结合参考稿内容修正其句内的重复/口误部分。
- edit_hint 仅供参考，以参考稿为准。

标点符号处理规则:
- 删除句尾标点符号 (句号、逗号、问号、感叹号、分号等)。每个片段的文本应以非标点字符结尾。
- 句中出现的标点符号替换为空格。

{{glossary}}
注意: 不要改变片段的原始时间戳 (start/end)。只修正文本内容使其与参考稿一致。

输出格式: JSON 数组，仅包含需要修正的片段:
[{"segment_id": "片段ID", "corrected_text": "修正后的文本", "changes": ["变更说明"], "category": "reference_aligned", "confidence": 0.0到1.0}]
无需修正的片段不要出现在输出中。
"""

_HIGHLIGHT_SYSTEM = """你是演讲视频内容分析师。用户以 JSON 格式提供转录片段列表。
请识别其中的高信息密度片段，用于生成精华版剪辑。

高信息密度片段包括:
- 核心论点和主要观点
- 关键数据、统计数字、实验结果
- 精彩类比、比喻、案例
- 重要结论和总结

上下文连贯性要求 (非常重要):
- 提取的片段最终会被拼接在一起播放，必须保证观众能看懂上下文逻辑。
- 如果一个片段依赖前文才成立 (如"所以他选择了离开"需要前一句才知道"他"是谁)，应将其依赖的上下文片段一并标记，而非只选孤立金句。
- 优先选择逻辑自成段落的连续片段组 (如一个完整论点从提出到总结的 2-3 个片段)，而非散落各处的单句。
- 避免选取过于碎片化、跳跃性大的片段，否则拼接后观众无法理解。

{{focus_keywords}}
输出格式: JSON 数组
[{"segment_id": "片段ID", "highlight_reason": "亮点理由 (含上下文关系说明)", "density": "high|medium"}]

只输出识别到的亮点片段 (含必要的上下文依赖片段)，普通内容不要输出。
用户会指定目标精华时长，请按信息密度优先级 (high > medium) 选取。
"""

_SEARCH_SYSTEM = """你是内容检索助手。用户以 JSON 格式提供转录片段列表和搜索查询。
请找出与查询语义最相关的片段 (不仅是字面匹配，包括语义关联)。

输出格式: JSON 数组，按相关度降序排列
[{"segment_id": "片段ID", "relevance": 0.0到1.0, "match_reason": "匹配原因"}]

只输出最相关的前 K 个片段，K 由用户指定。relevance 为 1.0 表示完全匹配，0.0 表示不相关。
"""

# v3.0.4 M1-3: {{target_language}} 不走 params 参数注入 -- 语言名由 handler
# 拿到 effective prompt 后用目标语言清单的英文显示名终替换 (占位符原样穿透
# get_effective_prompt 三层，见注册处注释)。
_TRANSLATION_SYSTEM = """You are a professional subtitle translator. The user provides a JSON payload containing a "segments" array (each item has an "id" and a source-language "text") and a "target_segment_ids" list naming the segments to translate. Translate the text of every target segment into {{target_language}}.

Rules:
- Translate exactly the segments whose ids appear in target_segment_ids. Segments outside that list are context only: use them to keep terminology and tone consistent, and never include them in the output.
- Output exactly one entry per target id -- as many entries as there are ids in target_segment_ids, in the same order. Do not add, drop, merge, or split entries.
- Echo each input id back unchanged in the "segment_id" field of its output entry. Never invent, alter, or reformat ids.
- Translate naturally and idiomatically for {{target_language}}, preserving the original meaning, tone, and register. Keep numbers, proper nouns, and technical terms accurate.

Output format: JSON array only -- no markdown fences, no explanations, no extra text of any kind.
[{"segment_id": "the unchanged input id", "translated_text": "the translation in {{target_language}}"}]
"""


# ------------------------------------------------------------------
# Default prompt registry
# ------------------------------------------------------------------

DEFAULT_PROMPTS: dict[str, dict[str, Any]] = {
    "smart_delete": {
        "system": _SMART_DELETE_SYSTEM,
        "params": {
            "custom_fillers": [],  # 自定义口头禅列表
        },
    },
    "subtitle_correction_a": {
        "system": _SUBTITLE_CORRECTION_SYSTEM_A,
        "params": {
            "glossary": [],  # 术语表
        },
    },
    "subtitle_correction_b": {
        "system": _SUBTITLE_CORRECTION_SYSTEM_B,
        "params": {
            "glossary": [],  # 术语表
        },
    },
    "highlight": {
        "system": _HIGHLIGHT_SYSTEM,
        "params": {
            "focus_keywords": [],  # 关注关键词
        },
    },
    "search": {
        "system": _SEARCH_SYSTEM,
        "params": {},  # 无参数化
    },
    "translation": {
        "system": _TRANSLATION_SYSTEM,
        # v3.0.4 M1-3 关键裁决: params 必须为 {} -- _inject_placeholders 只遍历
        # 注册 params 的 key，_format_param 对未注册 key 返回空串；若把
        # target_language 注册进 params，{{target_language}} 会被替换成空串、
        # 语言信息丢失。留空则占位符原样穿透三层覆盖，由 handler 终替换注入。
        "params": {},
    },
}


# ------------------------------------------------------------------
# Placeholder injection
# ------------------------------------------------------------------

def _format_param(key: str, value: list[str], func_key: str) -> str:
    """将参数值格式化为 prompt 中的可读文本。

    空值或仅含空白字符的值都替换为空字符串,保证 prompt 纯净。
    """
    # 过滤空白项,避免只有空格的参数被判定为有内容
    cleaned = [v.strip() for v in value if v and v.strip()]
    if not cleaned:
        return ""  # 空值 -> 空字符串
    # 按参数类型格式化
    if key == "custom_fillers":
        return f"\n额外需要检测的口头禅: {'、'.join(cleaned)}"
    elif key == "glossary":
        return f"\n参考术语表 (优先使用这些正确写法): {'、'.join(cleaned)}"
    elif key == "focus_keywords":
        return f"\n特别关注这些关键词的相关内容: {'、'.join(cleaned)}"
    return ""


def _inject_placeholders(prompt: str, params: dict, func_key: str) -> str:
    """将参数值替换到 prompt 中的 {{param}} 标记位。

    空值替换为空字符串，不影响 prompt 结构。
    非空值格式化为可读的补充指令段。
    """
    result = prompt
    for key, value in params.items():
        placeholder = f"{{{{{key}}}}}"
        if placeholder not in result:
            continue  # 该 prompt 无此标记位，跳过
        formatted = _format_param(key, value, func_key)
        result = result.replace(placeholder, formatted)
    return result


# ------------------------------------------------------------------
# Effective prompt resolution
# ------------------------------------------------------------------

def get_effective_prompt(
    func_key: str,
    project_prompts: dict | None = None,
) -> str:
    """获取生效的 system prompt，合并标记位参数注入。

    读取优先级: 项目覆盖 > 全局默认 > 硬编码常量

    Args:
        func_key: Prompt key (see DEFAULT_PROMPTS keys).
        project_prompts: Project-level overrides from Timeline.llm_prompts.
            If None or func_key not present, falls back to global settings.

    Returns:
        The effective system prompt string with placeholders resolved.
    """
    default = DEFAULT_PROMPTS.get(func_key)
    if default is None:
        logger.warning(f"Unknown prompt key: {func_key}")
        return ""

    # Load global settings lazily (avoid circular import at module load)
    from core.config import load_settings

    settings = load_settings()
    global_prompts = settings.get("llm_prompts", {})
    global_override = global_prompts.get(func_key, {})

    # 项目级覆盖优先
    if project_prompts and func_key in project_prompts:
        override = project_prompts[func_key]
    else:
        override = global_override

    # 高级模式: 使用 system_override (如果存在且非空)
    system_override = override.get("system_override")
    if system_override and system_override.strip():
        return system_override

    # 简单模式: 标记位替换
    system = default["system"]
    # 浅拷贝合并 (Shallow Merge) -- 安全: 参数结构仅一层 list[str]
    # 如未来参数结构嵌套更深层,需改用 Deep Merge
    params = {**default["params"], **override.get("params", {})}
    return _inject_placeholders(system, params, func_key)


def get_default_prompt_text(func_key: str) -> str:
    """获取指定功能的默认 prompt 原文 (含标记位)。

    用于前端"查看默认值"参考展示。
    """
    default = DEFAULT_PROMPTS.get(func_key)
    if default is None:
        return ""
    return default["system"]


def get_default_params(func_key: str) -> dict[str, list[str]]:
    """获取指定功能的默认参数定义。

    用于前端简单模式表单渲染。
    """
    default = DEFAULT_PROMPTS.get(func_key)
    if default is None:
        return {}
    return default["params"]
