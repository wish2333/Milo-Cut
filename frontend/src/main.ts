import { createApp } from "vue"
import App from "./App.vue"
import { isDemoMode, waitForPyWebView } from "./bridge"
import "./style.css"

const mount = () => createApp(App).mount("#app")

if (isDemoMode()) {
  mount()
} else {
  waitForPyWebView()
  .then(() => createApp(App).mount("#app"))
  .catch((err) => {
    console.error("Bridge init failed:", err)
    mount()
  })
}
