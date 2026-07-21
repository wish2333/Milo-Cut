import { onUnmounted, type Ref } from "vue"

interface DemoPlaybackOptions {
  currentTime: Ref<number>
  duration: Ref<number>
  paused: Ref<boolean>
  playbackRate: Ref<number>
  enabled: boolean
}

export function useDemoPlayback(options: DemoPlaybackOptions) {
  let frame: number | null = null
  let lastTimestamp = 0

  function stop() {
    if (frame !== null) cancelAnimationFrame(frame)
    frame = null
    lastTimestamp = 0
  }

  function tick(timestamp: number) {
    if (options.paused.value || !options.enabled) {
      stop()
      return
    }
    if (lastTimestamp === 0) lastTimestamp = timestamp
    const elapsed = (timestamp - lastTimestamp) / 1000
    lastTimestamp = timestamp
    const next = options.currentTime.value + elapsed * options.playbackRate.value
    if (next >= options.duration.value) {
      options.currentTime.value = options.duration.value
      options.paused.value = true
      stop()
      return
    }
    options.currentTime.value = next
    frame = requestAnimationFrame(tick)
  }

  function play() {
    if (!options.enabled) return
    if (options.currentTime.value >= options.duration.value) options.currentTime.value = 0
    options.paused.value = false
    stop()
    frame = requestAnimationFrame(tick)
  }

  function pause() {
    options.paused.value = true
    stop()
  }

  function toggle() {
    if (options.paused.value) play()
    else pause()
  }

  function seek(time: number, autoplay = false) {
    options.currentTime.value = Math.max(0, Math.min(options.duration.value, time))
    if (autoplay) play()
  }

  onUnmounted(stop)

  return { play, pause, toggle, seek, stop }
}

