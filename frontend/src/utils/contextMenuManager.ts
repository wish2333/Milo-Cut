type CloseFn = () => void

let activeClose: CloseFn | null = null
let cleanupDocument: (() => void) | null = null

function closeActive() {
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

function handleExternalClose() {
  closeActive()
}

export function openContextMenu(closeFn: CloseFn) {
  // v2.1.1 A-01: broadcast close to other independent menus (e.g. Waveform)
  window.dispatchEvent(new CustomEvent("closeallcontextmenus"))

  closeActive()
  activeClose = closeFn

  setTimeout(() => {
    document.addEventListener("click", handleDocClick, { once: true })
    document.addEventListener("contextmenu", handleDocContextMenu, { once: true })
    document.addEventListener("scroll", handleScroll, { capture: true, once: true })
    // v2.1.1 A-01: listen for close broadcasts from other components
    window.addEventListener("closeallcontextmenus", handleExternalClose, { once: true })
    cleanupDocument = () => {
      document.removeEventListener("click", handleDocClick)
      document.removeEventListener("contextmenu", handleDocContextMenu)
      document.removeEventListener("scroll", handleScroll, { capture: true })
      window.removeEventListener("closeallcontextmenus", handleExternalClose)
    }
  }, 0)
}

export function closeContextMenu() {
  closeActive()
}
