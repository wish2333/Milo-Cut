# Development

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) -- Python package manager
- [bun](https://bun.sh/) or [npm](https://nodejs.org/) -- frontend package manager

## Quick Start

```bash
# Windows
dev.bat

# macOS / Linux
./dev.sh
```

Both scripts call `uv run dev.py`, which does:

1. `uv sync` -- install Python dependencies
2. `npm install` -- install frontend dependencies
3. Start Vite dev server at `localhost:5173` (background)
4. Start `main.py` -- launch the pywebview window
5. Devtools open automatically

## Dev Modes

### Default (Vue + Vite)

```bash
uv run dev.py
```

- Starts Vite dev server at `localhost:5173` (background, hot reload)
- App connects to Vite for live updates
- Devtools open for inspection

### Disk Mode (production preview)

```bash
uv run dev.py --no-vite
```

- Skips Vite, loads `frontend_dist/index.html` from disk
- Use this to test the production build

### Custom Frontend

```bash
uv run dev.py --frontend-dir ./my-vue-app
```

Points to a different Vue project root (has `package.json`).

### Setup Only

```bash
uv run dev.py --setup
```

Installs all dependencies without starting the app.

## Writing Your App

### 1. Edit `main.py`

Define your Bridge subclass with `@expose` methods:

```python
from pywebvue import App, Bridge, expose

class MyApi(Bridge):
    @expose
    def get_data(self) -> dict:
        return {"success": True, "data": [1, 2, 3]}

if __name__ == "__main__":
    api = MyApi()
    app = App(api, title="My App", frontend_dir="frontend_dist")
    app.run()  # auto-detect: dev when not frozen, prod when frozen
```

`App()` constructor options:

| Param | Default | Description |
|---|---|---|
| `bridge` | -- | Your `Bridge` subclass instance |
| `title` | `"App"` | Window title |
| `width` / `height` | `800` / `600` | Window size in pixels |
| `frontend_dir` | `"frontend_dist"` | Built frontend directory |
| `dev_url` | `"http://localhost:5173"` | Vite dev server URL |
| `tick_interval` | `50` | JS timer interval (ms) for event/task processing |
| `on_start` | `None` | Callback before window creation (for DLL preloading) |

`App.run()` behavior:
- `dev=True` (default when not frozen) -- connects to `localhost:5173`
- `dev=False` (default when frozen) -- loads `{frontend_dir}/index.html` from disk
- `dev=None` -- same as auto-detect

### 2. Edit `frontend/src/App.vue`

The demo uses Vue 3 Composition API with `<script setup>`:

```vue
<script setup lang="ts">
import { call, onEvent, waitForPyWebView } from "./bridge";

onMounted(async () => {
  await waitForPyWebView();
  onEvent<{ count: number }>("tick", ({ count }) => {
    console.log(count);
  });
});

async function doSomething() {
  const res = await call<string>("my_method", "arg");
  if (res.success) console.log(res.data);
}
</script>
```

Bridge functions are in `frontend/src/bridge.ts`:
- `call<T>(method, ...args)` -- call an `@expose` Python method
- `onEvent<T>(name, handler)` -- listen for Python events, returns cleanup function
- `waitForPyWebView(timeout?)` -- wait for bridge ready
- `ApiResponse<T>` -- response type interface

### 3. Add new Python methods

In `main.py`, add methods to your Bridge subclass:

```python
class MyApi(Bridge):
    @expose
    def new_method(self, arg: str) -> dict:
        return {"success": True, "data": f"got {arg}"}
```

Then call from Vue:

```ts
const res = await call<string>("new_method", "hello")
```

## Thread Safety

### Event emission from background threads

``_emit()`` is thread-safe. It queues events internally; a JS timer flushes
them on the main thread. This is essential on Windows where WebView2 requires
``evaluate_js`` to be called from the main thread.

```python
import threading

def worker(app: App):
    while True:
        time.sleep(1)
        app.emit("progress", {"percent": 50})  # safe from any thread

threading.Thread(target=worker, args=(app,), daemon=True).start()
```

### Main-thread task execution

Some C++ extensions (e.g., ONNX Runtime, sherpa-onnx) must be initialized
on the main thread. Use ``register_handler`` + ``run_on_main_thread``:

```python
class MyApi(Bridge):
    def __init__(self):
        super().__init__()
        self.register_handler("init_recognizer", self._init_recognizer)

    def _init_recognizer(self, args):
        # Runs on the main thread -- safe for C++ extensions
        return sherpa_onnx.OnlineRecognizer.from_paraformer(args)

    def start_recognition(self):
        # From a background thread:
        recognizer = self.run_on_main_thread("init_recognizer", config_path)
```

### Windows C++ extension integration

If your project uses C++ extensions that share DLLs with WebView2 (e.g.,
ONNX Runtime), preload them before WebView2 initializes:

```python
# Option 1: Import before pywebvue (recommended)
import sherpa_onnx  # preload DLLs first

from pywebvue import App, Bridge, expose

# Option 2: Use on_start callback
App(api, on_start=lambda: preload_native_libs())
```

## Frontend Structure

```
frontend/
  index.html           Vite entry point
  package.json         Vue app dependencies
  vite.config.ts       Vite config (builds to ../frontend_dist/)
  src/
    main.ts            Vue bootstrap
    App.vue            Root component (edit this)
    bridge.ts          Bridge: call(), onEvent(), waitForPyWebView()
    env.d.ts           pywebview type declarations
```

## Production Build

```bash
cd frontend
npm run build      # or: bun run build
```

Output goes to `frontend_dist/` in the project root. Then:

```bash
uv run build.py    # PyInstaller bundles frontend_dist/ into the app
```
