- [x] macos端设置页检测的硬件编码器正常，但是导出设置中编码器列表仍是intel、amd、nvidia编码器（合理怀疑在无硬件编码器的win设备中也仍然会返回这些编码器）

- [ ] A-2.1点击字幕高亮：目前只有点击Waveform中的字幕才会使Timeline中的字幕高亮，而在Timeline及其侧边栏中点击均不会使字幕高亮。时间指针处的字幕也需要高亮，并且冻结时间指针处的字幕之外的其他字幕的右键菜单中从指针出分割的选项

- [ ] A-2.2修改字幕文本的过程中，想要拖动多选文字，但是一旦拖动超过编辑框就自动关闭编辑模式了

- [ ] A-2.4分割字幕之后两段字幕的标记是同步的，这需要拆开来

- [ ] Timeline侧边栏目前位置不太对，现在在Timeline里面，我希望他与Timeline平行排布，需要可以隐藏（添加一个小按钮隐藏/显示）并默认隐藏，其显示不会影响Timeline排版（在Timeline上一层）

- [ ] A-4.2右键点击重命名之后整个多Timeline选项区域会隐藏，需要重新打开编辑。A-4.4删除时也会隐藏；A-4.1新建\A-4.5切换Timeline时却没有立即隐藏

- [ ] C1.1分析之后没有信息返回到GUI中，后台日志显示已成功。这导致无法检查后续问题，现进入修复

  ```
  2026-06-24 10:24:49.934 | INFO     | core.project_service:save_project:245 - Saved project to Q:\Git\GithubManager\Milo-Cut\data\projects\20260514-潘多拉之心第二卷卷评\project.json
  2026-06-24 10:24:49.937 | INFO     | core.file_protocol:publish:100 - Published 112 records to 20260624_102449_edit_timeline.milo.jsonl
  2026-06-24 10:25:27.308 | INFO     | core.llm_service:call_llm:169 - LLM call completed: model=deepseek-v4-flash, tokens=1893, attempts=1
  2026-06-24 10:25:28.804 | INFO     | core.llm_service:call_llm:169 - LLM call completed: model=deepseek-v4-flash, tokens=2511, attempts=1
  2026-06-24 10:25:32.711 | INFO     | core.llm_service:call_llm:169 - LLM call completed: model=deepseek-v4-flash, tokens=2561, attempts=1
  2026-06-24 10:25:32.831 | INFO     | core.llm_service:call_llm:169 - LLM call completed: model=deepseek-v4-flash, tokens=2167, attempts=1
  2026-06-24 10:25:39.201 | INFO     | core.llm_service:call_llm:169 - LLM call completed: model=deepseek-v4-flash, tokens=3096, attempts=1
  2026-06-24 10:25:39.643 | INFO     | core.llm_service:call_llm:169 - LLM call completed: model=deepseek-v4-flash, tokens=2878, attempts=1
  2026-06-24 10:25:39.662 | INFO     | core.llm_service:call_llm:169 - LLM call completed: model=deepseek-v4-flash, tokens=3258, attempts=1
  2026-06-24 10:25:39.663 | INFO     | core.llm_service:analyze_smart_delete:658 - Smart-delete analysis done: 27 results, tokens=18364
  2026-06-24 10:25:39.663 | INFO     | core.project_service:add_analysis_results:1178 - Added 27 analysis results from llm_smart
  2026-06-24 10:25:41.693 | INFO     | core.project_service:save_project:245 - Saved project to Q:\Git\GithubManager\Milo-Cut\data\projects\20260514-潘多拉之心第二卷卷评\project.json
  2026-06-24 10:25:41.696 | INFO     | core.file_protocol:publish:100 - Published 112 records to 20260624_102541_edit_timeline.milo.jsonl
  ```

  