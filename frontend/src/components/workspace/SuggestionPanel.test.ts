/**
 * v3.0.4 M4-3 (P3-7): SuggestionPanel manual-range group + timecode popover.
 *
 * Host coverage (SPEC M4-3 table row 1 + M4-2 timecode entry):
 *  1. manual group lifecycle -- pending entry renders `删除/保留 {时长}s`
 *     + status badge, confirm flows to update_edit_decision (edit id +
 *     "confirmed"), confirmed props swap updates the badge;
 *  2. confirm wording -- the manual confirm control carries
 *     「确认 = 参与裁剪计算」(title);
 *  3. group delete -- delete_edit_decisions_batch is called and
 *     pushSnapshot(["edits"]) fires BEFORE the bridge call (order);
 *  4. timecode entry -- the header-bar `+ 时间码` button is always
 *     rendered (empty project included), invalid input (end<=start /
 *     empty) is rejected in place with NO bridge call, valid input runs
 *     the injected handler (snapshot -> add_range_decision -> patch out);
 *  5. legacy silence / llm_smart groups and the header counters keep
 *     their behavior (manual counts in, both actions included).
 *
 * The harness wires the REAL useAnalysis composable exactly as production
 * does (SuggestionPanel @confirm-edit/... -> Timeline relay rename ->
 * WorkspacePage binding -> useAnalysis), so the bridge assertions hit the
 * production call path. The injected range creator is a 1:1 replica of
 * WorkspacePage.handleRangeDecision -- the production injection target is
 * itself covered for the bubble entry by WorkspacePage.rangeDecision.test.ts
 * (P3-6 host).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils"
import { defineComponent, h, nextTick, provide, ref } from "vue"
import type { PropType } from "vue"
import SuggestionPanel from "./SuggestionPanel.vue"
import { useAnalysis } from "@/composables/useAnalysis"
import { mockEditDecision, mockProject, mockTimeline, mockSegment } from "@/test/helpers/mockProject"
import type { EditDecision, Project } from "@/types/project"

// ---------------------------------------------------------------------------
// Bridge mock: call capture (order via invocationCallOrder) + no-op events
// ---------------------------------------------------------------------------
const callMock = vi.fn()
const pushSnapshotMock = vi.fn()
/** Patches streamed out by the range-creation replica (project-updated). */
const patchesOut: unknown[] = []

vi.mock("@/bridge", () => ({
  call: (...args: unknown[]) => callMock(...args),
  onEvent: () => () => {},
  isDemoMode: () => false,
}))

// ---------------------------------------------------------------------------
// Harness: SuggestionPanel + the REAL useAnalysis, wired like production
// ---------------------------------------------------------------------------
const Harness = defineComponent({
  name: "SuggestionPanelHarness",
  components: { SuggestionPanel },
  props: {
    edits: { type: Array as PropType<EditDecision[]>, default: () => [] },
  },
  setup(props) {
    // Non-null project fixture: useAnalysis snapshots/assigns through it.
    const projectRef = ref<Project | null>(
      mockProject({
        timelines: [
          mockTimeline({
            id: "tl-1",
            transcript: {
              engine: "srt",
              language: "zh-CN",
              segments: [mockSegment({ id: "seg-1", start: 0, end: 60 })],
              tracks: [],
              bindings: [],
            },
          }),
        ],
        active_timeline_id: "tl-1",
      }),
    )
    const analysis = useAnalysis(projectRef, pushSnapshotMock)

    // 1:1 replica of WorkspacePage.handleRangeDecision (the production
    // injection target): snapshot BEFORE the write, patch out through the
    // project-updated channel, toast on failure (omitted -- no toast here).
    async function handleRangeDecision(payload: { start: number; end: number; action: "delete" | "keep" }) {
      if (!projectRef.value) return
      pushSnapshotMock(projectRef.value, ["edits"], "手动范围")
      const res = await callMock("add_range_decision", payload.start, payload.end, payload.action)
      if (res.success && res.data) patchesOut.push(res.data)
    }
    provide("suggestion:add-range-decision", handleRangeDecision)

    return () =>
      h(SuggestionPanel, {
        analysisResults: [],
        segments: [],
        edits: props.edits,
        // Same wiring as Timeline.vue:781-785 + WorkspacePage.vue:1546-1550.
        onConfirmEdit: (id: string) => void analysis.confirmEdit(id),
        onRejectEdit: (id: string) => void analysis.rejectEdit(id),
        onDeleteEditBatch: (ids: string[]) => void analysis.deleteEdits(ids),
      })
  },
})

// ---------------------------------------------------------------------------
// Fixtures / helpers
// ---------------------------------------------------------------------------
function manualEdit(overrides: Partial<EditDecision> = {}): EditDecision {
  return mockEditDecision({
    id: "edit-manual-aa11bb22",
    start: 2,
    end: 5,
    action: "delete",
    source: "manual",
    status: "pending",
    target_type: "range",
    target_id: undefined,
    ...overrides,
  })
}

function mountPanel(edits: EditDecision[]): VueWrapper {
  return mount(Harness, { props: { edits } })
}

/** Expanded-group item rows (direct children of the divide-y container). */
function itemRows(wrapper: VueWrapper) {
  return wrapper.findAll(".divide-y > div")
}

function findItemRow(wrapper: VueWrapper, label: string) {
  const row = itemRows(wrapper).find(r => r.text().includes(label))
  expect(row, `item row containing "${label}"`).toBeTruthy()
  return row!
}

async function openTimecode(wrapper: VueWrapper) {
  await wrapper.find('[data-test="timecode-toggle"]').trigger("click")
  const popover = wrapper.find('[data-test="timecode-popover"]')
  expect(popover.exists()).toBe(true)
  return popover
}

beforeEach(() => {
  callMock.mockReset()
  pushSnapshotMock.mockReset()
  patchesOut.length = 0
  callMock.mockImplementation(async () => ({ success: true, data: {} }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = "" // teleported context menus
})

// ---------------------------------------------------------------------------

describe("SuggestionPanel manual-range group (M4-3, P3-7)", () => {
  it("lifecycle: pending entry renders 删除 3.0s + badge, confirm calls update_edit_decision(id, confirmed), confirmed props swap the badge", async () => {
    const wrapper = mountPanel([manualEdit()])
    const panel = wrapper.getComponent(SuggestionPanel)

    // Group header + pending entry (manual group is expanded by default).
    expect(wrapper.text()).toContain("手动范围")
    const row = findItemRow(wrapper, "删除 3.0s")
    expect(row.find('[title="待处理"]').exists()).toBe(true)

    // Confirm -> panel emit -> (relay) -> useAnalysis -> bridge.
    const confirmBtn = row.findAll("button").find(b => b.text() === "确认")
    expect(confirmBtn).toBeTruthy()
    await confirmBtn!.trigger("click")
    expect(panel.emitted("confirm-edit")).toEqual([["edit-manual-aa11bb22"]])
    await flushPromises()
    expect(callMock).toHaveBeenCalledWith("update_edit_decision", "edit-manual-aa11bb22", "confirmed")

    // Confirmed props -> [Y] badge, pending badge and confirm button gone.
    await wrapper.setProps({ edits: [manualEdit({ status: "confirmed" })] })
    await nextTick()
    const confirmedRow = findItemRow(wrapper, "删除 3.0s")
    expect(confirmedRow.find('[title="已确认"]').exists()).toBe(true)
    expect(confirmedRow.find('[title="待处理"]').exists()).toBe(false)
    expect(confirmedRow.findAll("button").find(b => b.text() === "确认")).toBeUndefined()
    wrapper.unmount()
  })

  it("confirm wording: the manual confirm control carries 确认 = 参与裁剪计算 (delete and keep variants)", async () => {
    const wrapper = mountPanel([
      manualEdit({ id: "edit-manual-keep1", start: 1, end: 2, action: "keep" }),
      manualEdit({ id: "edit-manual-del1", start: 10, end: 12, action: "delete" }),
    ])
    const keepRow = findItemRow(wrapper, "保留 1.0s")
    const delRow = findItemRow(wrapper, "删除 2.0s")
    const keepConfirm = keepRow.findAll("button").find(b => b.text() === "确认")!
    const delConfirm = delRow.findAll("button").find(b => b.text() === "确认")!
    expect(keepConfirm.attributes("title")).toContain("确认 = 参与裁剪计算")
    expect(keepConfirm.attributes("title")).toContain("保留区间将从自动裁剪中扣除")
    expect(delConfirm.attributes("title")).toContain("确认 = 参与裁剪计算")
    wrapper.unmount()
  })

  it("group delete: delete_edit_decisions_batch is called with the manual ids and pushSnapshot(['edits']) fires BEFORE the call (order)", async () => {
    const confirmSpy = vi.fn(() => true)
    vi.stubGlobal("confirm", confirmSpy)
    const wrapper = mountPanel([manualEdit({ id: "edit-manual-del9" }), manualEdit({ id: "edit-manual-del8", start: 8, end: 9 })])

    // Group context menu (teleported to body).
    const header = wrapper.findAll("button").find(b => b.text().includes("手动范围"))
    expect(header).toBeTruthy()
    await header!.trigger("contextmenu")
    await nextTick()
    const menuDelete = [...document.body.querySelectorAll("button")]
      .find(b => b.textContent?.includes("删除本组建议"))
    expect(menuDelete).toBeTruthy()
    menuDelete!.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(callMock).toHaveBeenCalledTimes(1)
    expect(callMock).toHaveBeenCalledWith(
      "delete_edit_decisions_batch",
      ["edit-manual-del9", "edit-manual-del8"],
    )
    // Snapshot BEFORE the irreversible delete (useAnalysis.deleteEdits).
    expect(pushSnapshotMock).toHaveBeenCalledTimes(1)
    expect(pushSnapshotMock).toHaveBeenCalledWith(expect.anything(), ["edits"], "编辑决策")
    const pushOrder = pushSnapshotMock.mock.invocationCallOrder[0]
    const callOrder = callMock.mock.invocationCallOrder[0]
    expect(pushOrder).toBeLessThan(callOrder)
    wrapper.unmount()
  })
})

describe("SuggestionPanel timecode popover (M4-3 / SPEC M4-2 entry)", () => {
  it("the + 时间码 entry is always rendered (no manual data) and invalid input is rejected in place without any bridge call", async () => {
    const wrapper = mountPanel([]) // empty project-side edits
    expect(wrapper.text()).toContain("共 0 处建议")

    const toggle = wrapper.find('[data-test="timecode-toggle"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain("+ 时间码")
    await toggle.trigger("click")
    expect(wrapper.find('[data-test="timecode-popover"]').exists()).toBe(true)

    // end <= start -> in-place error, no bridge call, popover stays open.
    await wrapper.find('[data-test="timecode-start"]').setValue("10")
    await wrapper.find('[data-test="timecode-end"]').setValue("10")
    await wrapper.find('[data-test="timecode-submit"]').trigger("click")
    expect(wrapper.find('[data-test="timecode-error"]').text()).toContain("结束时间必须大于开始时间")
    expect(callMock).not.toHaveBeenCalled()
    expect(pushSnapshotMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="timecode-popover"]').exists()).toBe(true)

    // Empty field -> same in-place rejection.
    await wrapper.find('[data-test="timecode-start"]').setValue("")
    await wrapper.find('[data-test="timecode-end"]').setValue("5")
    await wrapper.find('[data-test="timecode-submit"]').trigger("click")
    expect(wrapper.find('[data-test="timecode-error"]').text()).toContain("请输入有效的起止时间")
    expect(callMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("valid input: snapshot(['edits'], 手动范围) BEFORE add_range_decision, default action delete, the patch streams out and the popover closes", async () => {
    const patch = { revision: 9, edits: [manualEdit({ id: "edit-manual-new01", start: 2.5, end: 7 })] }
    callMock.mockImplementation(async (method: string) => {
      if (method === "add_range_decision") return { success: true, data: patch }
      return { success: true, data: {} }
    })
    const wrapper = mountPanel([])
    await openTimecode(wrapper)

    await wrapper.find('[data-test="timecode-start"]').setValue("2.5")
    await wrapper.find('[data-test="timecode-end"]').setValue("7")
    await wrapper.find('[data-test="timecode-submit"]').trigger("click")
    await flushPromises()

    expect(pushSnapshotMock).toHaveBeenCalledTimes(1)
    expect(pushSnapshotMock).toHaveBeenCalledWith(expect.anything(), ["edits"], "手动范围")
    expect(callMock).toHaveBeenCalledWith("add_range_decision", 2.5, 7, "delete")
    expect(pushSnapshotMock.mock.invocationCallOrder[0]).toBeLessThan(
      callMock.mock.invocationCallOrder[0],
    )
    // The edits patch leaves through the project-updated channel.
    expect(patchesOut).toEqual([patch])
    // Optimistic close after a valid submit.
    expect(wrapper.find('[data-test="timecode-popover"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("keep choice: the delete/keep toggle submits action=keep; counters include manual keep entries alongside the two legacy groups", async () => {
    const edits: EditDecision[] = [
      mockEditDecision({ id: "ed-sil", start: 0, end: 1.5, source: "silence_detection" }),
      mockEditDecision({ id: "ed-smart", start: 4, end: 5.5, source: "llm_smart" }),
      manualEdit({ id: "ed-keep", start: 6, end: 7.5, action: "keep" }),
    ]
    const wrapper = mountPanel(edits)

    // Header counters: all three sources count, manual keep included.
    expect(wrapper.text()).toContain("共 3 处建议")
    expect(wrapper.text()).toContain("3 处待处理")
    // The two legacy groups keep their labels; manual is the third.
    for (const label of ["静音检测", "智能删除", "手动范围"]) {
      expect(wrapper.findAll("button").some(b => b.text().includes(label))).toBe(true)
    }
    // Legacy row labels unchanged (silence group needs expanding first).
    const silenceHeader = wrapper.findAll("button").find(b => b.text().includes("静音检测"))!
    await silenceHeader.trigger("click")
    expect(findItemRow(wrapper, "静音 1.5s").exists()).toBe(true)
    expect(findItemRow(wrapper, "智能删除 1.5s").exists()).toBe(true)
    expect(findItemRow(wrapper, "保留 1.5s").exists()).toBe(true)

    // Keep choice in the popover -> action=keep reaches the bridge.
    await openTimecode(wrapper)
    await wrapper.find('[data-test="timecode-start"]').setValue("3")
    await wrapper.find('[data-test="timecode-end"]').setValue("4.5")
    await wrapper.find('[data-test="timecode-action-keep"]').trigger("click")
    await wrapper.find('[data-test="timecode-submit"]').trigger("click")
    await flushPromises()
    expect(callMock).toHaveBeenCalledWith("add_range_decision", 3, 4.5, "keep")
    wrapper.unmount()
  })
})
