<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { api, connectWS, type RuntimeState, type Video } from "./api";
import Listen from "./views/Listen.vue";
import Library from "./views/Library.vue";
import Settings from "./views/Settings.vue";

const tab = ref<"listen" | "library" | "settings">("listen");
const state = ref<RuntimeState | null>(null);
const videos = ref<Video[]>([]);
const logs = ref<string[]>([]);
const progress = reactive<Record<string, { bytes: number; total: number }>>({});
const dlStatus = reactive<Record<string, string>>({});
const busy = ref(false);
const mode = ref<"played" | "all">("played"); // 本次播放过 / 全部历史
const target = ref<any>(null);
const tplink = ref("");

async function loadVideos() {
  videos.value = await api.videos({ played: mode.value === "played" });
}
async function refresh() {
  state.value = await api.state();
  await loadVideos();
}
function setMode(m: "played" | "all") {
  mode.value = m;
  loadVideos();
}

function pushLog(msg: string) {
  logs.value.unshift(`[${new Date().toLocaleTimeString()}] ${msg}`);
  if (logs.value.length > 400) logs.value.pop();
}

async function toggleListening() {
  if (!state.value) return;
  busy.value = true;
  try {
    if (state.value.proxy_running) await api.stopProxy();
    else await api.startProxy();
  } finally {
    busy.value = false;
    await refresh();
  }
}

async function installCert() {
  busy.value = true;
  try {
    await fetch(location.origin + "/api/cert/install", { method: "POST" }).catch(() => {});
  } finally {
    busy.value = false;
    await refresh();
  }
}

onMounted(async () => {
  await refresh();
  const ws = connectWS((e) => {
    if (e.type === "video") {
      loadVideos();
    } else if (e.type === "played" || e.type === "focused") {
      loadVideos();
    } else if (e.type === "target") {
      target.value = e;
      loadVideos();
    } else if (e.type === "progress") {
      progress[e.object_id] = { bytes: e.bytes, total: e.total };
    } else if (e.type === "download") {
      dlStatus[e.object_id] = e.status;
      if (e.status === "done") pushLog(`✅ 已保存：${e.path}`);
      if (e.status === "error") pushLog(`❌ 下载失败：${e.error}`);
    } else if (e.type === "log") {
      pushLog(e.msg);
    } else if (e.type === "proxy") {
      if (state.value) state.value.proxy_running = e.running;
    }
  });
  ws.onclose = () => pushLog("与核心的连接已断开");
});
</script>

<template>
  <div class="app">
    <aside class="sidebar">
      <div class="brand"><span class="dot" /> wxvideo <small>by zangle</small></div>
      <div class="nav">
        <button :class="{ active: tab === 'listen' }" @click="tab = 'listen'">监听 / 下载</button>
        <button :class="{ active: tab === 'library' }" @click="tab = 'library'">库与历史</button>
        <button :class="{ active: tab === 'settings' }" @click="tab = 'settings'">设置</button>
      </div>
      <div class="foot">v0.1.0 · 本地运行</div>
    </aside>

    <main class="main">
      <div class="topbar">
        <span class="pill" :class="state?.proxy_running ? 'ok' : ''">抓包 {{ state?.proxy_running ? "开启" : "关闭" }}</span>
        <span class="pill" :class="state?.cert.installed ? 'ok' : 'bad'">证书 {{ state?.cert.installed ? "已信任" : "未安装" }}</span>
        <span class="pill">代理 :{{ state?.proxy_port }}</span>
        <div class="spacer" />
        <button class="btn" :disabled="busy" @click="refresh">刷新</button>
        <button class="btn primary" :class="{ listening: state?.proxy_running }" :disabled="busy" @click="toggleListening">
          {{ state?.proxy_running ? "停止监听" : "开始监听" }}
        </button>
      </div>

      <div class="content">
        <Listen v-if="tab === 'listen'" :videos="videos" :mode="mode" :target="target" :progress="progress" :dl-status="dlStatus" @refresh="refresh" @mode="setMode" />
        <Library v-else-if="tab === 'library'" :videos="videos" :dl-status="dlStatus" />
        <Settings v-else :state="state" :logs="logs" @refresh="refresh" @install-cert="installCert" />
      </div>
    </main>
  </div>
</template>
