/**
 * v3.0.4 M1-6: shared constants for "translate into a new secondary track".
 *
 * The list mirrors the backend `_TRANSLATION_LANGUAGES` registry (main.py):
 * BCP-47 short codes = the `SubtitleTrack.language` fill-value convention.
 * Kept in one place so the panel dialog, the estimated-batch entry and any
 * later consumer never drift apart. No emoji (repo convention).
 */
export interface TranslationLanguageOption {
  /** BCP-47 short code, also the backend validation key. */
  code: string
  /** English display name (matches backend prompt injection). */
  name: string
}

export const TRANSLATION_LANGUAGES: TranslationLanguageOption[] = [
  { code: "en", name: "English" },
  { code: "ja", name: "Japanese" },
  { code: "ko", name: "Korean" },
  { code: "zh-CN", name: "Simplified Chinese" },
  { code: "zh-TW", name: "Traditional Chinese" },
  { code: "fr", name: "French" },
  { code: "de", name: "German" },
  { code: "es", name: "Spanish" },
  { code: "ru", name: "Russian" },
]

/** Matches the backend settings default for `llm_translation_target_language`. */
export const DEFAULT_TRANSLATION_LANGUAGE = "en"

export function isTranslationLanguage(code: unknown): code is string {
  return typeof code === "string"
    && TRANSLATION_LANGUAGES.some((l) => l.code === code)
}

/**
 * Completion notice kept for panel display after the closed-loop watcher in
 * WorkspacePage consumed the singleton completion ref (M1-6): uncovered ids
 * must be surfaced explicitly, never silently dropped.
 */
export interface TranslationNotice {
  trackName: string
  language: string
  uncoveredIds: string[]
}
