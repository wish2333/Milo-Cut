import { createApp } from "vue"
import App from "./App.vue"
import { waitForPyWebView } from "./bridge"
import "./style.css"

waitForPyWebView()
  .then(() => createApp(App).mount("#app"))
  .catch((err) => {
    console.error("Bridge init failed:", err)
    createApp(App).mount("#app")
  })
