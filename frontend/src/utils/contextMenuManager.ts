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

export function openContextMenu(closeFn: CloseFn) {
  closeActive()
  activeClose = closeFn

  setTimeout(() => {
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
