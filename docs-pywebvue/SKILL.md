---
description: "PyWebVue framework: Python + pywebview + Vue bridge. Use when working on this project for development, building, or extending functionality."
---

# PyWebVue Project Skill

Use this skill when working on the **pywebvue-framework** project.

## What This Project Is

A minimal "clone and develop" Python + Vue bridge framework built on [pywebview](https://github.com/r0x0r/pywebview). NOT an installable package -- users clone and start coding.

## Key Files

| File | Role |
|---|---|
| `main.py` | App entry point. Edit this to define your Bridge subclass. |
| `frontend/src/App.vue` | Root Vue component. Edit this for the frontend UI. |
| `frontend/src/bridge.ts` | Bridge functions: `call()`, `onEvent()`, `waitForPyWebView()`. |
| `pywebvue/app.py` | App class: window creation, dev/prod URL resolution, lifecycle. |
| `pywebvue/bridge.py` | Bridge base class + `@expose` decorator. Core Python<->JS communication. |
| `dev.py` | Dev startup: installs deps, starts Vite, starts app. |
| `build.py` | Packaging: PyInstaller (desktop) + Buildozer (Android). |
| `app.spec` | PyInstaller spec. Edit `[MODIFY]` sections for custom builds. |

## Common Tasks

### Add a new exposed Python method

1. Open `main.py`, find your `Bridge` subclass
2. Add a method decorated with `@expose`
3. Return `{"success": True, "data": ...}` on success

```python
@expose
def get_items(self) -> dict:
    return {"success": True, "data": self._items}
```

### Call it from Vue

```ts
// In App.vue or any component
import { call } from "./bridge"
const res = await call<string[]>("get_items")
if (res.success) { /* use res.data */ }
```

### Push events from Python to JS

```python
# In a Bridge method or background thread (thread-safe):
self._emit("my_event", {"status": "done"})

# Via App instance (from outside Bridge):
app.emit("my_event", {"status": "done"})
```

Frontend listens:

```ts
import { onEvent } from "./bridge"
const off = onEvent<{ status: string }>("my_event", ({ status }) => {
    console.log(status)
})
// later: off() to remove listener
```

### Run the app

```bash
uv run dev.py              # Start Vite + app (default)
uv run dev.py --no-vite    # Load frontend_dist/ from disk
```

### Build for distribution

```bash
cd frontend && npm run build   # Build Vue app -> frontend_dist/
uv run build.py                # Desktop onedir -> dist/app/
uv run build.py --onefile      # Desktop single exe -> dist/app.exe
uv run build.py --android      # Android APK (macOS/Linux)
```

## Patterns & Conventions

### Response envelope (required)

All `@expose` methods must return:
```python
{"success": True, "data": <result>}
# On error (automatic via @expose):
{"success": False, "error": "description"}
```

### Event naming

Python emits: `app.emit("progress", ...)` or `self._emit("progress", ...)`
TS receives: `onEvent("progress", handler)` -- the `pywebvue:` prefix is added automatically.

### Dev vs Prod modes

- `app.run()` with no args: auto-detects via `sys.frozen` (dev from source, prod when PyInstaller frozen)
- `app.run(dev=True)`: connects to Vite dev server at `localhost:5173`
- `app.run(dev=False)`: loads `index.html` from `frontend_dir` on disk
- `debug` param is independent: controls devtools (default: open in dev env)

### File drag-and-drop

Built-in: native file paths captured via `Bridge.get_dropped_files()`.

## Dependencies

- Python >= 3.10
- pywebview >= 6.0 (auto-installed by uv)
- uv (package manager)
- bun or npm (frontend)

## Python API Quick Reference

```python
from pywebvue import App, Bridge, expose

# App(bridge, *, title, width, height, min_size, frontend_dir, dev_url,
#     tick_interval=50, on_start=None)
# App.run(dev=None, *, debug=None)
# App.emit(event, data=None)
# App.dev -> bool (True when not frozen)

# class MyApi(Bridge):
#     @expose def method(self, ...) -> dict
#     self._emit(event, data)              # thread-safe event push
#     self.register_handler(name, handler)  # register main-thread handler
#     self.run_on_main_thread(name, args, timeout=30)  # schedule on main thread
#     self.get_dropped_files() -> {"success": True, "data": [...paths]}
```

## TypeScript API Quick Reference

```typescript
import { call, onEvent, waitForPyWebView, ApiResponse } from "./bridge"

// call<T>(method, ...args): Promise<ApiResponse<T>>
// onEvent<T>(name, handler: (detail: T) => void): () => void  // returns cleanup
// waitForPyWebView(timeout?): Promise<void>
// interface ApiResponse<T> { success: boolean; data?: T; error?: string }
```
