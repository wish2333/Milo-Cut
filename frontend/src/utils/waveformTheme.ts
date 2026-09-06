/**
 * Waveform canvas palette (v3.0.0 M9-2).
 *
 * Canvas 2D cannot use CSS classes, so the waveform drawing colors live here
 * as the single source instead of being hardcoded at each call site. Values
 * mirror the Tailwind slate scale used elsewhere in the waveform UI.
 * Business templates must not hardcode hex colors (styleLint test locks
 * this); new colors should be added here with a semantic name.
 */
export const WAVEFORM_COLORS = {
  /** Waveform peak fill (slate-400). */
  peak: "#94a3b8",
  /** Waveform peak outline (slate-500). */
  peakStroke: "#64748b",
} as const
