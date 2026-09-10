/**
 * v3.0.5 R5.6 (M5.6 ruling 3): export confirmation page states the
 * keep/delete overlap semantics in a hover-free static line under the
 * confirmed-edits count row.
 *
 * Covers:
 *  1. with confirmed delete edits -> the line 「保留区间与删除区间重叠时，
 *     导出按删除处理」 is rendered as visible text (not a title);
 *  2. with no confirmed edits -> the line is absent (empty-project export
 *     header stays clean).
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount } from "@vue/test-utils"
import ExportPage from "./ExportPage.vue"
import { mockEditDecision, mockProject, mockTimeline } from "@/test/helpers/mockProject"
import type { EditDecision, Project } from "@/types/project"

const callMock = vi.fn()

vi.mock("@/bridge", () => ({
  call: (...args: unknown[]) => callMock(...args),
  onEvent: () => () => {},
  isDemoMode: () => false,
}))

function projectWithEdits(edits: EditDecision[]): Project {
  return mockProject({
    timelines: [
      mockTimeline({
        id: "tl-1",
        edits,
      }),
    ],
    active_timeline_id: "tl-1",
  })
}

function mountPage(project: Project) {
  return mount(ExportPage, {
    props: { project },
    global: {
      stubs: { EncodingSettings: true, PreviewPlayer: true, EditSummaryModal: true },
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  callMock.mockResolvedValue({ success: false })
})

describe("ExportPage keep/delete overlap note (v3.0.5 R5.6)", () => {
  it("renders the hover-free overlap note when confirmed delete edits exist", () => {
    const wrapper = mountPage(
      projectWithEdits([
        mockEditDecision({ id: "e-1", action: "delete", status: "confirmed", start: 1, end: 2 }),
      ]),
    )
    expect(wrapper.text()).toContain("保留区间与删除区间重叠时，导出按删除处理")
    wrapper.unmount()
  })

  it("hides the note when there are no confirmed delete edits", () => {
    const wrapper = mountPage(projectWithEdits([]))
    expect(wrapper.text()).not.toContain("保留区间与删除区间重叠时")
    wrapper.unmount()
  })
})
