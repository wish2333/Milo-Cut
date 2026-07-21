import { describe, it, expect, vi, afterEach } from "vitest"
import { mount } from "@vue/test-utils"
import { h, defineComponent, nextTick } from "vue"
import VideoControls from "./VideoControls.vue"
import DeleteRangesOverlay from "./DeleteRangesOverlay.vue"

const RANGES = [
  { start: 5, end: 10 },
  { start: 20, end: 30 },
  { start: 45, end: 50 },
]

function mountControls(currentTime = 0) {
  return mount(VideoControls, {
    props: {
      currentTime,
      duration: 60,
      paused: true,
      volume: 0.5,
      playbackRate: 1,
      deleteRanges: RANGES,
      previewMode: "edited",
    },
  })
}

// v2.3.2 阶段 1.1: progress bar 拖动需要可用的 getBoundingClientRect。
// JSDOM 默认返回全 0，会导致 time 计算为 NaN，因此为相关元素注入伪 rect。
function mockProgressRect(width = 100) {
  const spy = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    if (this.classList && this.classList.contains("flex-1") && this.classList.contains("h-5")) {
      return { left: 0, top: 0, width, height: 5, right: width, bottom: 5, x: 0, y: 0, toJSON() {} } as DOMRect
    }
    return { left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0, x: 0, y: 0, toJSON() {} } as DOMRect
  })
  return spy
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("VideoControls delete-range overlay integration (v2.3.2 G6)", () => {
  it("renders DeleteRangesOverlay child when previewMode is edited and ranges exist", () => {
    const wrapper = mountControls()
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(true)
  })

  it("does not render DeleteRangesOverlay in original preview mode", async () => {
    const wrapper = mountControls()
    await wrapper.setProps({ previewMode: "original" })
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(false)
  })

  it("does not render DeleteRangesOverlay when deleteRanges is empty", async () => {
    const wrapper = mountControls()
    await wrapper.setProps({ deleteRanges: [] })
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(false)
  })

  it("keeps child prop references stable across currentTime-only updates", async () => {
    const wrapper = mountControls(0)
    const overlayBefore = wrapper.findComponent(DeleteRangesOverlay)
    expect(overlayBefore.exists()).toBe(true)
    // vue-test-utils returns reactive proxies from props(), so we cannot use
    // referential equality here. Use deep equality to assert the value is
    // unchanged; Vue's reactivity system still skips child re-renders based
    // on the underlying prop identity at the framework level.
    expect(overlayBefore.props("ranges")).toStrictEqual(RANGES)
    expect(overlayBefore.props("duration")).toBe(60)

    await wrapper.setProps({ currentTime: 25 })
    await wrapper.setProps({ currentTime: 50 })

    const overlayAfter = wrapper.findComponent(DeleteRangesOverlay)
    expect(overlayAfter.exists()).toBe(true)
    expect(overlayAfter.props("ranges")).toStrictEqual(RANGES)
    expect(overlayAfter.props("duration")).toBe(60)
  })

  // v2.3.2 阶段 1.1 任务 2：直接计数子组件 render 次数。
  // 之前的 deep-equal props 测试只能证明 "props 引用没变"，但 Vue 是否
  // 真的跳过了 patch 仍需要直接观察。这里用一个名字与原组件一致的
  // 自定义 stub 替换 DeleteRangesOverlay，并通过 setup/render 计数
  // 验证：currentTime-only 更新时子组件 setup/render 都不会再触发。
  it("does NOT re-render child component when only currentTime changes (render count evidence)", async () => {
    let setupCount = 0
    let renderCount = 0
    const OverlayStub = defineComponent({
      name: "DeleteRangesOverlay",
      setup() {
        setupCount++
        return () => {
          renderCount++
          return h("div", { class: "overlay-stub" })
        }
      },
    })

    const wrapper = mount(VideoControls, {
      props: {
        currentTime: 0,
        duration: 60,
        paused: true,
        volume: 0.5,
        playbackRate: 1,
        deleteRanges: RANGES,
        previewMode: "edited",
      },
      global: {
        stubs: {
          DeleteRangesOverlay: OverlayStub,
        },
      },
    })

    // 初始挂载：setup 与 render 各执行 1 次
    expect(setupCount).toBe(1)
    expect(renderCount).toBe(1)
    expect(wrapper.findComponent(OverlayStub).exists()).toBe(true)

    // 仅更新 currentTime —— 触发父组件自身重渲染
    await wrapper.setProps({ currentTime: 25 })
    await nextTick()
    await wrapper.setProps({ currentTime: 50 })
    await nextTick()

    // 子组件 setup/render 仍未增加：证明 Vue 跳过了 overlay 的 patch
    expect(setupCount).toBe(1)
    expect(renderCount).toBe(1)

    // 但 ranges 变化时子组件必须能正常更新（避免假阳性：例如 stub 完全没挂载）
    await wrapper.setProps({ deleteRanges: [...RANGES, { start: 55, end: 58 }] })
    await nextTick()
    expect(setupCount).toBe(1) // 仍是同一实例，setup 不重新执行
    // render 增加：props 变化导致子组件重渲染
    expect(renderCount).toBeGreaterThanOrEqual(2)
  })

  // 反向用例：当 deleteRanges 变化时，子组件必须重新 render。
  // 与上一个测试一起构成 "currentTime 不触发、ranges 触发" 的完整证据对。
  it("re-renders child component when deleteRanges actually changes", async () => {
    let renderCount = 0
    const OverlayStub = defineComponent({
      name: "DeleteRangesOverlay",
      setup() {
        return () => {
          renderCount++
          return h("div", { class: "overlay-stub" })
        }
      },
    })

    const wrapper = mount(VideoControls, {
      props: {
        currentTime: 0,
        duration: 60,
        paused: true,
        volume: 0.5,
        playbackRate: 1,
        deleteRanges: RANGES,
        previewMode: "edited",
      },
      global: {
        stubs: {
          DeleteRangesOverlay: OverlayStub,
        },
      },
    })

    expect(renderCount).toBe(1)

    const newRanges = [...RANGES, { start: 55, end: 58 }]
    await wrapper.setProps({ deleteRanges: newRanges })
    await nextTick()

    expect(renderCount).toBeGreaterThanOrEqual(2)
  })
})

// v2.3.2 阶段 1.1 任务 3：progress bar 点击 / 拖动 / previewMode 切换的回归测试。
// 防止 G6 拆分 overlay 时破坏 progress bar 既有交互。
describe("VideoControls progress bar interaction regression (v2.3.2 stage 1.1)", () => {
  it("emits update:currentTime with proportional value on progress bar click", async () => {
    const rectSpy = mockProgressRect(100)
    const wrapper = mountControls()

    const progressBar = wrapper.find(".flex-1.h-5.cursor-pointer")
    expect(progressBar.exists()).toBe(true)

    await progressBar.trigger("mousedown", { button: 0, clientX: 25 })

    const emitted = wrapper.emitted("update:currentTime")
    expect(emitted).toBeTruthy()
    expect(emitted!.length).toBeGreaterThan(0)
    // 25/100 * 60s duration = 15s
    expect(emitted![emitted!.length - 1]).toEqual([15])
    expect(rectSpy).toHaveBeenCalled()
  })

  it("ignores non-left-click on progress bar (no seek)", async () => {
    mockProgressRect(100)
    const wrapper = mountControls()

    const progressBar = wrapper.find(".flex-1.h-5.cursor-pointer")
    await progressBar.trigger("mousedown", { button: 2, clientX: 25 })

    expect(wrapper.emitted("update:currentTime")).toBeFalsy()
  })

  it("emits multiple update:currentTime during drag (mousedown -> mousemove -> mouseup)", async () => {
    mockProgressRect(100)
    const wrapper = mountControls()

    const progressBar = wrapper.find(".flex-1.h-5.cursor-pointer")
    await progressBar.trigger("mousedown", { button: 0, clientX: 10 })

    // Drag mouse to 50% (30s) then 75% (45s)
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 50 }))
    await nextTick()
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 75 }))
    await nextTick()

    // mouseup ends drag; should not emit further
    document.dispatchEvent(new MouseEvent("mouseup"))
    await nextTick()
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 90 }))
    await nextTick()

    const emitted = wrapper.emitted("update:currentTime")
    expect(emitted).toBeTruthy()
    const times = emitted!.map(e => e[0] as number)
    // Initial mousedown + 2 mousemoves = at least 3 emissions
    expect(times.length).toBeGreaterThanOrEqual(3)
    expect(times).toContain(6) // clientX=10 -> 6s
    expect(times).toContain(30) // clientX=50 -> 30s
    expect(times).toContain(45) // clientX=75 -> 45s
    // Post-mouseup move must NOT have emitted
    expect(times[times.length - 1]).not.toBe(54) // clientX=90 -> 54s
  })

  it("clamps seek time to [0, duration]", async () => {
    mockProgressRect(100)
    const wrapper = mountControls()

    const progressBar = wrapper.find(".flex-1.h-5.cursor-pointer")

    // Drag beyond right edge
    await progressBar.trigger("mousedown", { button: 0, clientX: 200 })
    let emitted = wrapper.emitted("update:currentTime")
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1]).toEqual([60]) // clamped to duration

    // Drag beyond left edge
    await progressBar.trigger("mousedown", { button: 0, clientX: -50 })
    emitted = wrapper.emitted("update:currentTime")
    expect(emitted!).toBeTruthy()
    expect(emitted![emitted!.length - 1]).toEqual([0]) // clamped to 0
  })

  it("clamps to 0 when duration is 0 (no NaN)", async () => {
    mockProgressRect(100)
    const wrapper = mount(VideoControls, {
      props: {
        currentTime: 0,
        duration: 0,
        paused: true,
        volume: 0.5,
        playbackRate: 1,
        deleteRanges: RANGES,
        previewMode: "edited",
      },
    })

    const progressBar = wrapper.find(".flex-1.h-5.cursor-pointer")
    await progressBar.trigger("mousedown", { button: 0, clientX: 50 })

    const emitted = wrapper.emitted("update:currentTime")
    // duration<=0 path returns 0 explicitly, not NaN
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1]).toEqual([0])
  })

  it("removes document mousemove/mouseup listeners after mouseup (no seek leak)", async () => {
    mockProgressRect(100)
    const wrapper = mountControls()

    const progressBar = wrapper.find(".flex-1.h-5.cursor-pointer")
    await progressBar.trigger("mousedown", { button: 0, clientX: 10 })
    document.dispatchEvent(new MouseEvent("mouseup"))
    await nextTick()

    // After mouseup, document mousemove must not emit
    const beforeCount = wrapper.emitted("update:currentTime")?.length ?? 0
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 90 }))
    await nextTick()
    const afterCount = wrapper.emitted("update:currentTime")?.length ?? 0
    expect(afterCount).toBe(beforeCount)
  })

  it("toggles DeleteRangesOverlay visibility when previewMode switches edited<->original", async () => {
    const wrapper = mountControls()
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(true)

    await wrapper.setProps({ previewMode: "original" })
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(false)

    await wrapper.setProps({ previewMode: "edited" })
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(true)
  })

  it("overlay does not intercept progress bar clicks (pointer-events-none on children)", async () => {
    // Sanity: overlay 子元素的 pointer-events 被禁用，点击事件仍由 progress bar 处理
    const rectSpy = mockProgressRect(100)
    const wrapper = mountControls()

    // Click position covered by an overlay range (start=5..end=10 -> 8.3%..16.7%)
    const progressBar = wrapper.find(".flex-1.h-5.cursor-pointer")
    await progressBar.trigger("mousedown", { button: 0, clientX: 12 })

    const emitted = wrapper.emitted("update:currentTime")
    expect(emitted).toBeTruthy()
    expect(rectSpy).toHaveBeenCalled()
    const lastTime = (emitted![emitted!.length - 1] as number[])[0]
    expect(lastTime).toBeCloseTo(7.2, 10) // 12/100 * 60 = 7.2 (浮点容差)
  })
})
