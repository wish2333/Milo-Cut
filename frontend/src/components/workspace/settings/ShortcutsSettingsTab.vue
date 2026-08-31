<template>
  <!-- Shortcuts reference tab (v3.0.0 M8-1, extracted from SettingsModal.vue).
       Pure static content: no state, no events. -->
  <div class="space-y-6">
    <!-- 播放控制 -->
    <section>
      <h3 class="text-sm font-semibold text-gray-700 mb-3">播放控制</h3>
      <div class="space-y-2">
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">从当前行播放视频</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Space</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">原片 / 剪后切换预览</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Space</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">跳到片段开头</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">I</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">跳到片段结尾</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">O</kbd>
          </div>
        </div>
      </div>
    </section>

    <!-- 编辑操作 -->
    <section>
      <h3 class="text-sm font-semibold text-gray-700 mb-3">编辑操作</h3>
      <div class="space-y-2">
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">标记删除</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Delete</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">撤销上一步</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Z</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">保存项目</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">S</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">打开搜索替换</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">F</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">上下移动选中行</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↑</kbd>
            <span class="text-gray-400 mx-1">/</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↓</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">多选字幕行</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <span class="text-gray-600">Click</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 时间微调 -->
    <section>
      <h3 class="text-sm font-semibold text-gray-700 mb-3">时间微调（时间编辑 input 聚焦时）</h3>
      <div class="space-y-2">
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">+0.1s / +1.0s (Shift)</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↑</kbd>
            <span class="text-xs text-gray-400">(Shift+↑)</span>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">-0.1s / -1.0s (Shift)</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↓</kbd>
            <span class="text-xs text-gray-400">(Shift+↓)</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 建议面板 -->
    <section>
      <h3 class="text-sm font-semibold text-gray-700 mb-3">建议面板</h3>
      <div class="space-y-2">
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">全部确认建议</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">A</kbd>
          </div>
        </div>
        <div class="flex items-center justify-between py-1.5">
          <span class="text-gray-600">忽略所有建议</span>
          <div class="flex items-center gap-1">
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
            <span class="text-gray-400 mx-1">+</span>
            <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">D</kbd>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
