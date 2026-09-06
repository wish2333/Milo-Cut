# PROJECT_SCHEMA.md — project.json 字段契约

> 适用于 v2 multi-timeline schema（`schema_version: 2`）。落盘位置：`data/projects/<name>/project.json`。
> v3.0.0 M2 起附带持久化安全契约（fsync + 双备份 + 恢复链，见文末）。

## 顶层结构（core/models.py: Project）

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | int = 2 | 结构版本；`_migrate_to_v2` 负责 v1 → v2 |
| `project` | ProjectMeta | `name` / `created_at` / `updated_at`（ISO 字符串） |
| `media` | MediaInfo \| null | 媒体信息（见下） |
| `timelines` | list[Timeline] | 多时间线容器；至少一条（构造器保证） |
| `active_timeline_id` | str | 必须指向 `timelines` 中某条（构造器修复） |

## MediaInfo

`path`（必填）、`media_hash`（指纹，relink 时更新）、`duration`(s, float)、`format`、`width/height/fps/pix_fmt`、`audio_channels/sample_rate/bit_rate`、`proxy_path`、`waveform_path`。

## Timeline

| 字段 | 说明 |
|---|---|
| `id` | 唯一 id（`default` / `tl_<ms>` / fork id） |
| `label` / `source` / `created_at` / `parent_id` | 元数据；source ∈ manual/fork/llm_p0/llm_p1/migrated |
| `transcript` | TranscriptData（见下） |
| `edits` | list[EditDecision] |
| `analysis` | AnalysisData（`last_run` + `results[]`） |
| `llm_prompts` | 时间线级 prompt 覆盖（smart_delete 等键） |

## TranscriptData

- `engine: str = "srt"`（v3.0.0 M1-1 起由转写写入 whisper/qwen3-asr 等）
- `language: str = "zh-CN"`
- `segments: list[Segment]`，**主轨按 start 升序**（sort invariant，`_enforce_segment_sort_invariant` 保证；v3.0.0 M11-2 起契约锁定**只管主轨**，副轨各 track 自维护有序）
- `tracks: list[SubtitleTrack]`（v3.0.0 M11-2）：只读副轨。`{id: trk_<hex8>, role: extension|translation|caption, name, language, segments}`；副轨段 id 命名空间隔离为 `track_{track_id}_seg_{start:.3f}`，防止 merge/决策系统与主轨误匹配
- `bindings: list[TrackBinding]`（v3.0.0 M11-2）：主轨段 ↔ 副轨段绑定（`{id: bind_<hex8>, track_id, main_segment_id, extension_segment_id, start_offset, end_offset}`，offset = 副轨 − 主轨，秒）。**本版只写不消费**（导入时 300ms 起点容差贪心匹配生成，一对一）；联动编辑/解绑交互推迟到 v3.1
- ProjectPatch 对应 `tracks` / `bindings` 两层（timeline 内层组，整体替换语义，前端按 id in-place 合并保持引用稳定），见 `core/project_patch.py` / `frontend/src/utils/projectPatch.ts`
- v3.0.1：新增可选 `meta: dict`（旁路载荷，如联动消解计数 `{linkage: {squeezed, removed, unbound}}`）；缺省 None，旧前端忽略

## Segment

`id`（ASR: `seg_{start:.3f}`；SRT 导入: `seg-0001` 顺序号；split: `{id}-a/-b`）、`version`、`type`（subtitle/silence，无 gap）、`start`/`end`（float 秒，round3）、`text`、`words: list[Word]`（`{word,start,end,confidence}`）、`speaker`、`dirty_flags`。

词级规则（v3.0.0 M1-2）：split 后两段 words 拼接 = 原段（对齐成功）或双空（不可靠切点，宁可缺失不可错位）；merge 后 words 按 start 排序拼接。

## EditDecision

`id`、`start`/`end`、`action`（delete/keep）、`source`、`analysis_id`、`status`（pending/confirmed/rejected）、`priority`、`target_type`（segment/range）、`target_id`（segment 型必填）。

## 迁移链（ProjectService._open_internal 打开时依序执行）

1. `_migrate_to_v2`：v1 平铺结构（顶层 transcript/edits/analysis）→ 包装进 default Timeline；`schema_version` 1→2
2. `_migrate_silence_edits`：旧静音 ED 绑定 target_id
3. `_dedupe_edit_ids`：去重重复 ED id（v2.1.1）
4. `_migrate_highlights`：legacy highlight ED 迁移（v2.1.1）
5. `_migrate_overlapping_silence_edits`：重叠静音 ED 修复（v2.1.2）

## 持久化安全契约（v3.0.0 M2，core/persistence.py）

- 保存：tmp 写入 → flush+fsync → 备份轮换（`project.json.bak.1` ← 当前，`bak.2` ← 旧 bak.1，copy 语义）→ `os.replace` → 目录 fsync（尽力而为）。备份/目录 fsync 失败仅告警不阻断保存。
- 打开：主文件 JSON 损坏或校验失败 → 依次尝试 `.bak.1`、`.bak.2`；全部失败返回 `{"success": false, "error": "项目文件损坏且无可用备份", "data": {"tried": [...]}}`；从备份恢复成功时 envelope 附带 `recovered_from`（前端 toast 提示）。
- 变更模型时的规则：只增字段且带默认值；禁止重建 `TranscriptData(...)`（用 `model_copy(update=)`），否则会静默丢 engine/language/tracks 等元数据。

## 导出边界

- 视频导出（segment-concat 管线）只消费主轨 segments/edits；SRT/VTT 导出由 export_srt 生成；OTIO/EDL/FCPXML/Premiere XML 由 export_timeline 生成（audio-only fps=0 安全）。
- **副轨（tracks）不参与视频导出与时间轴裁剪映射**（v3.0.0 M11-2）：确认删除/keep-range 只作用于主轨；副轨 SRT 通过 `export_subtitle` 任务携带 `track_id` 单独导出（v3.0.1 起走 `export_track_subtitle`：默认与主轨同一删除映射落到导出时间轴，`map_deletions=False` 时按原始时间戳直出；v3.0.2 移除了旧的 `export_track_srt` 直出包装），导出对话框按轨道逐个出按钮。
- v3.0.0 转写自动导出的 SRT（`data/transcripts/`）仅为归档交付物，**不再回读**（M1-1）。
