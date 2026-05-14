# /// script
# requires-python = ">=3.10"
# dependencies = ["pywebview>=6.0"]
# ///
"""PyWebVue demo - clone and run."""

import time
import threading

from pywebvue import App, Bridge, expose


class DemoApi(Bridge):
    @expose
    def greet(self, name: str) -> dict:
        return {"success": True, "data": f"Hello, {name}!"}

    @expose
    def add(self, a: float, b: float) -> dict:
        return {"success": True, "data": a + b}

    @expose
    def get_info(self) -> dict:
        return {
            "success": True,
            "data": {
                "python": "OK",
                "time": time.strftime("%H:%M:%S"),
            },
        }


def _start_counter(app: App) -> None:
    """Push a tick event to frontend every second."""
    count = 0
    while True:
        time.sleep(1)
        count += 1
        app.emit("tick", {"count": count})


if __name__ == "__main__":
    api = DemoApi()
    app = App(api, title="PyWebVue Demo", frontend_dir="frontend_dist")
    threading.Thread(target=_start_counter, args=(app,), daemon=True).start()
    app.run()
