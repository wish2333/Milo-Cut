import { ref } from "vue"
import { call } from "@/bridge"

export interface LlmConnectionResult {
  model: string
  response_time_ms: number
}

const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)

export function useLlmSettings() {
  async function testConnection(): Promise<boolean> {
    testing.value = true
    testResult.value = null

    const res = await call<LlmConnectionResult>("test_llm_connection")
    testing.value = false

    if (res.success && res.data) {
      testResult.value = {
        success: true,
        message: `Connected to ${res.data.model} (${res.data.response_time_ms}ms)`,
      }
      return true
    }

    testResult.value = {
      success: false,
      message: res.error ?? "Connection failed",
    }
    return false
  }

  return {
    testing,
    testResult,
    testConnection,
  }
}
