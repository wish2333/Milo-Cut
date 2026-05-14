<script setup lang="ts">
import { ref, onMounted } from "vue";
import { call, onEvent, waitForPyWebView } from "./bridge";

const name = ref("World");
const greetResult = ref("waiting...");
const numA = ref(3);
const numB = ref(5);
const addResult = ref("waiting...");
const infoResult = ref("waiting...");
const counter = ref(0);
const ready = ref(false);

onMounted(async () => {
  try {
    await waitForPyWebView();
    ready.value = true;
  } catch (err) {
    greetResult.value = `Failed: ${(err as Error).message}`;
  }

  // Listen for Python -> JS tick events
  onEvent<{ count: number }>("tick", ({ count }) => {
    counter.value = count;
  });
});

async function greet() {
  const res = await call<string>("greet", name.value);
  greetResult.value = res.success ? res.data! : `Error: ${res.error}`;
}

async function add() {
  const res = await call<number>("add", Number(numA.value), Number(numB.value));
  addResult.value = res.success
    ? `${numA.value} + ${numB.value} = ${res.data}`
    : `Error: ${res.error}`;
}

async function getInfo() {
  const res = await call<{ python: string; time: string }>("get_info");
  infoResult.value = res.success ? JSON.stringify(res.data, null, 2) : `Error: ${res.error}`;
}
</script>

<template>
  <div class="card">
    <h1>PyWebVue Demo</h1>

    <section class="section">
      <label>Greet (Python)</label>
      <div class="row">
        <input v-model="name" type="text" placeholder="Your name" />
        <button @click="greet">Send</button>
      </div>
      <pre class="result">{{ greetResult }}</pre>
    </section>

    <section class="section">
      <label>Add (Python)</label>
      <div class="row">
        <input v-model.number="numA" type="number" />
        <input v-model.number="numB" type="number" />
        <button @click="add">Add</button>
      </div>
      <pre class="result">{{ addResult }}</pre>
    </section>

    <section class="section">
      <label>Backend Info</label>
      <button @click="getInfo">Get Info</button>
      <pre class="result">{{ infoResult }}</pre>
    </section>

    <div class="status" :class="{ ok: ready }">
      Python -> JS tick event: <span class="counter">{{ counter }}</span>
    </div>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
body {
  font-family: -apple-system, "Microsoft YaHei", sans-serif;
  background: #1a1a2e;
  color: #e0e0e0;
  display: flex;
  justify-content: center;
  padding: 40px 20px;
  min-height: 100vh;
}
.card {
  background: #16213e;
  border-radius: 12px;
  padding: 32px;
  width: 100%;
  max-width: 440px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
}
h1 {
  font-size: 22px;
  margin-bottom: 24px;
  color: #e94560;
}
.section {
  margin-bottom: 20px;
}
label {
  display: block;
  font-size: 13px;
  color: #888;
  margin-bottom: 6px;
}
input,
.result {
  width: 100%;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #0f3460;
  font-size: 14px;
}
input {
  background: #0f3460;
  color: #fff;
  outline: none;
}
input:focus {
  border-color: #e94560;
}
.result {
  background: #0a0a1a;
  color: #53d769;
  font-family: monospace;
  min-height: 36px;
  margin-top: 8px;
  white-space: pre-wrap;
}
button {
  margin-top: 8px;
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  background: #e94560;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}
button:hover {
  background: #c73850;
}
.row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.row input {
  width: 80px;
}
.status {
  margin-top: 24px;
  font-size: 13px;
  color: #666;
  text-align: center;
}
.status.ok {
  color: #53d769;
}
.counter {
  color: #e94560;
  font-weight: bold;
}
</style>
