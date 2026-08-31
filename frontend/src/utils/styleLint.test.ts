/**
 * Style lint (v3.0.0 M9-2): source-level checks enforcing the layering
 * contract and template styling rules from docs/DESIGN.md.
 *
 * Locked rules:
 * 1. No raw z-index utilities (`z-[N]`, `z-10/20/50`...) in business
 *    components -- use the five token utilities (z-base/raised/dropdown/
 *    modal/toast). The only allowed definition site is style.css.
 * 2. No hardcoded hex colors in business .vue files -- use semantic tokens
 *    (Tailwind theme classes) or, for canvas drawing, `utils/waveformTheme`.
 *
 * Not yet enforced (v3.1 backlog, see record-3.0.0-P3-3): migrating the
 * legacy raw gray-scale classes (text-gray-*, bg-amber-*) to semantic
 * tokens -- the rule is documented for new code; the migration is a
 * mechanical sweep across every component.
 */
import { describe, it, expect } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

function collectFiles(dir: string, ext: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) collectFiles(full, ext, acc)
    else if (entry.endsWith(ext)) acc.push(full)
  }
  return acc
}

const SRC = join(process.cwd(), "src")
const vueSources = collectFiles(SRC, ".vue").map((f) => ({
  file: f.replace(SRC, "src"),
  src: readFileSync(f, "utf-8"),
}))
const styleCss = readFileSync(join(SRC, "style.css"), "utf-8")

describe("style lint (M9-2 layering + template rules)", () => {
  it("no raw z-index utilities in business .vue files", () => {
    const offenders: string[] = []
    for (const { file, src } of vueSources) {
      // arbitrary values like z-[9999] and the tailwind scale z-10..z-50
      const re = /(?:z-\[\d+\]|z-(?:10|20|30|40|50)\b)/
      if (re.test(src)) offenders.push(file)
    }
    expect(offenders).toEqual([])
  })

  it("no hardcoded hex colors in business .vue files", () => {
    const offenders: string[] = []
    for (const { file, src } of vueSources) {
      // 6/3-digit hex literal anywhere in the component (template/style/script)
      const re = /#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/
      if (re.test(src)) offenders.push(file)
    }
    expect(offenders).toEqual([])
  })

  it("token utilities exist in style.css (z-base..z-toast)", () => {
    const css = styleCss
    for (const token of ["--z-base", "--z-raised", "--z-dropdown", "--z-modal", "--z-toast"]) {
      expect(css).toContain(token)
    }
    for (const util of ["z-base", "z-raised", "z-dropdown", "z-modal", "z-toast"]) {
      expect(css).toContain(`@utility ${util}`)
    }
  })
})
