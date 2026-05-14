# API Reference

## Python

### `App`

```python
from pywebvue import App
```

Creates a pywebview window wired to a Bridge instance.

#### Constructor

```python
App(
    bridge: Bridge,
    *,
    title: str = "App",
    width: int = 800,
    height: int = 600,
    min_size: tuple[int, int] = (600, 400),
    frontend_dir: str = "frontend_dist",
    dev_url: str = "http://localhost:5173",
    tick_interval: int = 50,
    on_start: Callable[[], None] | None = None,
)
```

| Param | Default | Description |
|---|---|---|
| `bridge` | -- | Your `Bridge` subclass instance |
| `title` | `"App"` | Window title |
| `width` | `800` | Window width in pixels |
| `height` | `600` | Window height in pixels |
| `min_size` | `(600, 400)` | Minimum window size |
| `frontend_dir` | `"frontend_dist"` | Directory containing `index.html` (used when `dev=False`) |
| `dev_url` | `"http://localhost:5173"` | Vite dev server URL (used when `dev=True`) |
| `tick_interval` | `50` | JS timer interval in ms for event flushing and task execution |
| `on_start` | `None` | Callback invoked before `webview.create_window()`, useful for DLL preloading |

#### `run(dev=None, *, debug=None)`

Create the window and start the event loop.

| Param | Default | Description |
|---|---|---|
| `dev` | `None` | `True` = Vite dev server, `False` = disk, `None` = auto (dev when not frozen) |
| `debug` | `None` | Open developer tools. `None` = auto (True when not frozen) |

```python
app.run()           # auto-detect: dev + debug when not frozen, prod when frozen
app.run(dev=False)  # force load from disk (still opens devtools in dev env)
app.run(dev=True, debug=False)  # force connect to Vite, no devtools
```

#### `emit(event, data=None)`

Push an event to the frontend. Dispatches a `CustomEvent` named `pywebvue:{event}`.

```python
app.emit("progress", {"percent": 50})
```

#### `dev` (property)

`True` when not running inside a PyInstaller bundle.

---

### `Bridge`

```python
from pywebvue import Bridge
```

Base class for Python APIs exposed to the frontend.

```python
class MyApi(Bridge):
    def __init__(self):
        super().__init__()
        # self._window is set automatically by App

    @expose
    def my_method(self, arg: str) -> dict:
        return {"success": True, "data": f"got {arg}"}

    def push_to_frontend(self):
        self._emit("my_event", {"key": "value"})
```

#### `_emit(event, data=None)`

Dispatch a `CustomEvent` named `pywebvue:{event}` to the frontend. The `data` is serialized to JSON and attached as `event.detail`.

**Thread-safe**: can be called from any thread. Events are queued and flushed on the main thread via a periodic JS timer.

#### `get_dropped_files()`

Return file paths from the most recent drag-and-drop event and clear the buffer.

```python
result = self.get_dropped_files()
# result = {"success": True, "data": ["/path/to/file1.txt", ...]}
```

#### `register_handler(name, handler)`

Register a named handler for main-thread task execution. Handlers are called on the main thread when scheduled via ``run_on_main_thread``.

```python
class MyApi(Bridge):
    def __init__(self):
        super().__init__()
        self.register_handler("init_model", self._init_model)

    def _init_model(self, args):
        # This runs on the main thread -- safe for C++ extensions
        return sherpa_onnx.OnlineRecognizer.from_paraformer(args)
```

#### `run_on_main_thread(name, args=None, timeout=30.0)`

Schedule a registered handler on the main thread and block until completion. **Thread-safe**: can be called from background threads.

Raises `TimeoutError` if the task exceeds the timeout. Raises `RuntimeError` if the handler raises or is not registered.

```python
# From a background thread:
recognizer = self.run_on_main_thread("init_model", config_path)
```

---

### `@expose`

```python
from pywebvue import expose
```

Decorator that wraps a Bridge method with try/except. If the method raises an exception, it returns `{"success": False, "error": "..."}` instead of crashing.

```python
@expose
def divide(self, a: float, b: float) -> dict:
    return {"success": True, "data": a / b}
    # If b == 0, returns {"success": False, "error": "division by zero"}
```

**Convention**: exposed methods should return `{"success": True, "data": ...}`.

---

## Thread Safety

### Event emission

``_emit()`` is thread-safe. It queues events internally; a JS timer flushes them on the main thread. This avoids crashes on Windows where WebView2 requires ``evaluate_js`` to be called from the main thread.

### Main-thread task execution

Some C++ extensions (e.g., ONNX Runtime) must be initialized on the main thread. Use ``register_handler`` + ``run_on_main_thread``:

1. In ``__init__``, register handlers with ``self.register_handler(name, handler)``
2. From any background thread, call ``self.run_on_main_thread(name, args)`` to schedule and wait

### Windows C++ extension integration

If your project uses C++ extensions that share DLLs with WebView2 (e.g., ONNX Runtime), preload them before WebView2 initializes:

```python
# Option 1: Import before pywebvue
import sherpa_onnx  # preload DLLs first

from pywebvue import App, Bridge, expose

# Option 2: Use on_start callback
App(api, on_start=lambda: import_and_init_native_libs())
```

---

## TypeScript (Vue)

The bridge functions live in `frontend/src/bridge.ts` and are imported directly in Vue components.

```ts
import { call, onEvent, waitForPyWebView } from "./bridge"
```

### `call<T>(method, ...args): Promise<ApiResponse<T>>`

Call an `@expose`-decorated Python method.

```ts
const res = await call<string>("greet", "World")
if (res.success) {
    console.log(res.data)  // "Hello, World!"
}
```

### `onEvent<T>(name, handler): () => void`

Listen for events dispatched by `Bridge._emit()`. Returns a cleanup function.

```ts
const off = onEvent<{ percent: number }>("progress", ({ percent }) => {
    console.log(`${percent}%`)
})
// Later: off() to remove listener
```

### `waitForPyWebView(timeout?: number): Promise<void>`

Poll until `window.pywebview.api` is populated. Default timeout: 10 seconds.

```ts
await waitForPyWebView()
// Bridge is ready, safe to call Python methods
```

### `ApiResponse<T>`

```ts
interface ApiResponse<T = unknown> {
    success: boolean
    data?: T
    error?: string
}
```

---

## Response Convention

All Python -> JS communication uses a consistent envelope:

```json
{"success": true, "data": <any>}
```

On error (automatic via `@expose` or manual):

```json
{"success": false, "error": "description of what went wrong"}
```
