# Building & Packaging

## Desktop (PyInstaller)

### Quick Build

```bash
# Build frontend first
cd frontend && npm run build && cd ..

# Then package
uv run build.py            # onedir: folder containing exe + dependencies
uv run build.py --onefile  # onefile: single standalone executable
uv run build.py --clean    # remove build artifacts
```

Output goes to `dist/`.

### Configuration (`app.spec`)

Edit `app.spec` to customize your build. All user-configurable sections are marked `[MODIFY]`:

| Section | What to change |
|---|---|
| `ENTRY_SCRIPT` | Path to your main Python script |
| `APP_NAME` | Output executable name |
| Frontend assets | Which directory to bundle (default: `frontend_dist/`) |
| `ICON` | App icon (`.ico` for Windows, `.icns` for macOS) |
| `hiddenimports` | Additional Python packages to include |
| `EXCLUDES_*` | GUI frameworks to exclude (reduces size) |

### Frontend Bundling

The Vue app builds to `frontend_dist/`:

```bash
cd frontend
npm run build    # output: ../frontend_dist/index.html + assets
```

`app.spec` bundles `frontend_dist/` into the PyInstaller output.

### GUI Engine

pywebview auto-selects the best engine per platform:

| Platform | Engine |
|---|---|
| Windows | EdgeWebView2 (or CEF if no Edge) |
| macOS | Cocoa WebKit |
| Linux | GTK WebKit (requires `libwebkit2gtk-4.1-dev`) |

The spec excludes unused GUI frameworks (PyQt, PySide, tkinter) to reduce bundle size.

### Windows C++ Extensions

If your project uses C++ extensions (e.g., ONNX Runtime, sherpa-onnx) that share
DLLs with WebView2's Chromium engine, note:

- DLL load order matters: if ONNX Runtime DLLs are in the same directory as the
  executable, Windows may load the wrong MSVC runtime.
- Use the ``on_start`` callback to preload native libraries before WebView2
  initializes:

```python
App(api, on_start=lambda: preload_native_libs())
```

- Or import the native library before ``from pywebvue import App``.
- Add native extension DLLs to the ``hiddenimports`` or ``datas`` section in
  ``app.spec`` if they are not auto-detected.

---

## Android (Buildozer)

### Prerequisites

- macOS or Linux (not supported on Windows -- use WSL)
- [Buildozer](https://buildozer.readthedocs.io/): `pip install buildozer`
- Android SDK/NDK (auto-downloaded by Buildozer on first run)

### Build

```bash
uv run build.py --android
```

First run generates `buildozer.spec` automatically. Edit it before building:

| Section | Key fields |
|---|---|
| `[app]` | `title`, `package.name`, `package.domain`, `version` |
| `[app]` | `requirements` -- add your Python dependencies |
| `[app]` | `android.add_jars` -- pywebview JAR path (auto-resolved) |
| `[app:android]` | `android.api`, `android.minapi`, `android.permissions` |

### Android Limitations

- Single window only (no multi-window support)
- No window manipulation (resize, minimize, etc.)
- No file dialogs
- Uses `android.webkit.WebView`

### Manual JAR Resolution

If auto-resolution fails, find the JAR manually:

```bash
python -c "from webview import util; print(util.android_jar_path())"
```

Update `android.add_jars` in `buildozer.spec` with the output.
