import { call } from "@/bridge"
import type { Project } from "@/types/project"

export function useTranscript() {
  async function importSrt(filePath: string): Promise<Project | null> {
    const res = await call<Project>("import_srt", filePath)
    return res.success && res.data ? res.data : null
  }

  return {
    importSrt,
  }
}
