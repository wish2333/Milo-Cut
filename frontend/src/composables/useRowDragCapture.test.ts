/**
 * v3.0.2 M3-3 / P2-5: useRowDragCapture skeleton tests -- frozen-snapshot
 * semantics (row destroy never disturbs timeAt), the P4 dual mapping
 * (bounded/unbounded) delegated to timeFromPointerInRow, capture/release
 * lifecycle, re-capture overwrite, and the width<=0 degradation contract.
 */
import { describe, expect, it } from "vitest"
import { useRowDragCapture, type FrozenRowGeometry } from "./useRowDragCapture"

/** Known geometry: row 3 of a 10s grid over 100s media (200px wide). */
const GEOMETRY: FrozenRowGeometry = {
  rowLeft: 100,
  rowWidth: 200,
  rowStart: 30,
  rowSpan: { start: 30, end: 50 },
}

describe("useRowDragCapture lifecycle", () => {
  it("timeAt returns null before any capture", () => {
    const drag = useRowDragCapture()
    expect(drag.frozen.value).toBeNull()
    expect(drag.timeAt(200, { bounded: true })).toBeNull()
    expect(drag.timeAt(200, { bounded: false })).toBeNull()
  })

  it("release clears the snapshot; timeAt returns null afterwards", () => {
    const drag = useRowDragCapture()
    drag.capture(150, GEOMETRY)
    expect(drag.frozen.value).not.toBeNull()
    expect(drag.timeAt(200, { bounded: true })).toBe(40)
    drag.release()
    expect(drag.frozen.value).toBeNull()
    expect(drag.timeAt(200, { bounded: true })).toBeNull()
  })

  it("a second capture overwrites the previous geometry", () => {
    const drag = useRowDragCapture()
    drag.capture(150, GEOMETRY) // left=100, width=200, span 30..50
    drag.capture(0, { rowLeft: 0, rowWidth: 100, rowStart: 0, rowSpan: { start: 0, end: 10 } })
    expect(drag.frozen.value).toEqual({
      rowLeft: 0,
      rowWidth: 100,
      rowStart: 0,
      rowSpan: { start: 0, end: 10 },
    })
    // 50px into a 100px row spanning 0..10s -> 5s, not the old row's math.
    expect(drag.timeAt(50, { bounded: true })).toBe(5)
  })
})

describe("useRowDragCapture timeAt (P4 dual mapping via frozen snapshot)", () => {
  it.each([
    [200, true, 40], // mid-row: ratio 0.5 -> 30 + 0.5*20
    [200, false, 40],
    [50, true, 30], // before the row: bounded clamps left to span start
    [50, false, 25], // unbounded runs free: ratio -0.25 -> 30 - 5
    [100, true, 30], // exact left edge
    [300, true, 50], // exact right edge
    [400, true, 50], // past the row: bounded clamps right to span end
    [400, false, 60], // unbounded: ratio 1.5 -> 30 + 30
  ])("timeAt(%s, bounded=%s) = %s", (clientX, bounded, expected) => {
    const drag = useRowDragCapture()
    drag.capture(clientX, GEOMETRY)
    expect(drag.timeAt(clientX, { bounded })).toBe(expected)
  })
})

describe("useRowDragCapture snapshot semantics (row destroy immunity)", () => {
  it("mutating or replacing the caller's geometry object after capture does not affect timeAt", () => {
    const drag = useRowDragCapture()
    const geometry: FrozenRowGeometry = { ...GEOMETRY, rowSpan: { ...GEOMETRY.rowSpan } }
    // The slot mirrors the row component's reactive geometry reference.
    const slot: { geometry: FrozenRowGeometry | null } = { geometry }
    drag.capture(200, geometry) // slot.geometry === geometry at pointerdown
    // Simulate the row unmounting: its geometry object is mutated to junk...
    geometry.rowLeft = -999
    geometry.rowWidth = 0
    geometry.rowSpan.start = -1e9
    geometry.rowSpan.end = -1e9
    // ...and the row's slot is replaced by a fresh degenerate object.
    slot.geometry = { rowLeft: -1, rowWidth: 0, rowStart: -1, rowSpan: { start: -1, end: -1 } }
    expect(slot.geometry.rowWidth).toBe(0) // slot truly replaced
    expect(drag.frozen.value).not.toBe(slot.geometry)
    // Snapshot still maps the pointer continuously: 200 -> 40, 50 -> 25.
    expect(drag.timeAt(200, { bounded: false })).toBe(40)
    expect(drag.timeAt(50, { bounded: false })).toBe(25)
    expect(drag.timeAt(50, { bounded: true })).toBe(30)
  })

  it("frozen holds a defensive copy, not the caller's reference", () => {
    const drag = useRowDragCapture()
    const geometry: FrozenRowGeometry = { ...GEOMETRY, rowSpan: { ...GEOMETRY.rowSpan } }
    drag.capture(200, geometry)
    expect(drag.frozen.value).not.toBe(geometry)
    expect(drag.frozen.value?.rowSpan).not.toBe(geometry.rowSpan)
    expect(drag.frozen.value).toEqual(GEOMETRY)
  })
})

describe("useRowDragCapture degenerate-geometry defense", () => {
  it("width <= 0 snapshot degrades timeAt to null instead of throwing", () => {
    const drag = useRowDragCapture()
    // capture deliberately does not validate; a tearing-down row can read
    // width 0. timeFromPointerInRow would throw -- the kernel catches.
    drag.capture(200, { rowLeft: 100, rowWidth: 0, rowStart: 30, rowSpan: { start: 30, end: 50 } })
    expect(drag.frozen.value).not.toBeNull()
    expect(() => drag.timeAt(200, { bounded: true })).not.toThrow()
    expect(drag.timeAt(200, { bounded: true })).toBeNull()
    expect(drag.timeAt(200, { bounded: false })).toBeNull()
  })

  it.each([0, -50])("rowWidth=%s is defended for both mappings", width => {
    const drag = useRowDragCapture()
    drag.capture(200, { rowLeft: 0, rowWidth: width, rowStart: 0, rowSpan: { start: 0, end: 10 } })
    expect(drag.timeAt(50, { bounded: true })).toBeNull()
    expect(drag.timeAt(50, { bounded: false })).toBeNull()
  })
})
