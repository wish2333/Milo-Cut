export function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.round((seconds % 1) * 1000)
  if (h > 0) {
    return `${h}:${pad(m)}:${pad(s)}.${pad3(ms)}`
  }
  return `${pad(m)}:${pad(s)}.${pad3(ms)}`
}

export function formatTimeShort(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${pad(s)}`
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function pad(n: number): string {
  return n.toString().padStart(2, "0")
}

function pad3(n: number): string {
  return n.toString().padStart(3, "0")
}

/**
 * Parse a time string into seconds.
 * Accepts: "MM:SS.mmm", "MM:SS", "SS.mmm", "SS", "H:MM:SS.mmm"
 */
export function parseTime(input: string): number | null {
  const s = input.trim()
  if (!s) return null

  // Pure number -> treat as seconds
  if (/^\d+(\.\d+)?$/.test(s)) {
    return parseFloat(s)
  }

  // Split by ":"
  const parts = s.split(":")
  if (parts.length === 2) {
    const m = parseFloat(parts[0])
    const sec = parseFloat(parts[1])
    if (isNaN(m) || isNaN(sec)) return null
    return m * 60 + sec
  }
  if (parts.length === 3) {
    const h = parseFloat(parts[0])
    const m = parseFloat(parts[1])
    const sec = parseFloat(parts[2])
    if (isNaN(h) || isNaN(m) || isNaN(sec)) return null
    return h * 3600 + m * 60 + sec
  }

  return null
}
