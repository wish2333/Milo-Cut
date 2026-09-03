type CloseFn = () => void

// v3.0.0 M9-1: single-instance mutex -- module-level state is shared by every
// consumer, so opening a new menu closes the previous one. The former
// `closeallcontextmenus` window broadcast is gone: consumers register their
// close fn here instead of listening for global events.
let activeClose: CloseFn | null = null
let cleanupDocument: (() => void) | null = null
// Smoke-fix: a PENDING async registration from a previous menu must be
// cancelled, otherwise it lands after the new menu opened and its
// once-contextmenu listener instantly closes the new menu (reported:
// "通过右键关闭后打不开新的右键菜单").
let pendingRegister: ReturnType<typeof setTimeout> | null = null

function closeActive() {
  if (pendingRegister !== null) {
    clearTimeout(pendingRegister)
    pendingRegister = null
  }
  if (cleanupDocument) {
    cleanupDocument()
    cleanupDocument = null
  }
  if (activeClose) {
    activeClose()
    activeClose = null
  }
}

function handleDocClick() {
  closeActive()
}

function handleDocContextMenu() {
  closeActive()
}

function handleScroll() {
  closeActive()
}

export function openContextMenu(closeFn: CloseFn) {
  closeActive()
  activeClose = closeFn

  pendingRegister = setTimeout(() => {
    pendingRegister = null
    document.addEventListener("click", handleDocClick, { once: true })
    document.addEventListener("contextmenu", handleDocContextMenu, { once: true })
    document.addEventListener("scroll", handleScroll, { capture: true, once: true })
    cleanupDocument = () => {
      document.removeEventListener("click", handleDocClick)
      document.removeEventListener("contextmenu", handleDocContextMenu)
      document.removeEventListener("scroll", handleScroll, { capture: true })
    }
  }, 0)
}

export function closeContextMenu() {
  closeActive()
}
