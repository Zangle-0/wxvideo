<script setup lang="ts">
import { ref } from "vue";
import type { RuntimeState } from "../api";

const props = defineProps<{ state: RuntimeState | null; logs: string[] }>();
const emit = defineEmits<{ (e: "refresh"): void; (e: "install-cert"): void }>();

const dir = ref(props.state?.download_dir || "");
const msg = ref("");

async function call(path: string, body?: unknown) {
  const r = await fetch(location.origin + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  return r.json();
}

async function installCert() {
  msg.value = "正在安装根证书…（若弹系统确认请允许）";
  const r = await call("/api/cert/install");
  if (r && r.ok) {
    msg.value = `证书安装成功：${String(r.thumbprint || "").slice(0, 16)}…`;
  } else {
    msg.value = `安装失败：${String((r && (r.raw || r.error)) || "未知错误").slice(0, 200)}`;
  }
  emit("refresh");
}
async function uninstallCert() {
  const r = await call("/api/cert/uninstall");
  msg.value = r && r.ok ? "已卸载根证书" : "卸载失败（可能仍在使用）";
  emit("refresh");
}
async function restoreNet() {
  await call("/api/netguard/restore");
  msg.value = "已还原系统代理";
  emit("refresh");
}
async function saveDir() {
  await call("/api/settings", { download_dir: dir.value });
  msg.value = "下载目录已保存";
  emit("refresh");
}
async function doctor() {
  const r = await call("/api/doctor");
  msg.value = r.report || "自检完成";
}
</script>

<template>
  <div class="field">
    <label>下载目录</label>
    <div class="row">
      <input class="input" style="flex:1" v-model="dir" :placeholder="state?.download_dir" />
      <button class="btn" @click="saveDir">保存</button>
    </div>
  </div>

  <div class="field">
    <label>根证书（抓包必需）</label>
    <div class="row">
      <span class="pill" :class="state?.cert.installed ? 'ok' : 'bad'">
        {{ state?.cert.installed ? "已信任" : "未安装" }}
      </span>
      <button class="btn primary" :disabled="state?.cert.installed" @click="installCert">
        {{ state?.cert.installed ? "已安装" : "安装证书" }}
      </button>
      <button class="btn ghost" :disabled="!state?.cert.installed" @click="uninstallCert">
        卸载证书
      </button>
    </div>
    <div v-if="state?.cert?.thumbprint" class="meta">指纹：{{ state.cert.thumbprint }}</div>
  </div>

  <div class="field">
    <label>网络</label>
    <div class="row">
      <span class="pill" :class="state?.proxy_running ? 'ok' : ''">
        {{ state?.proxy.enabled ? "系统代理开启中" : "系统代理关闭" }}
      </span>
      <button class="btn" @click="restoreNet">一键恢复网络</button>
    </div>
  </div>

  <div class="field">
    <label>诊断</label>
    <div class="row">
      <button class="btn" @click="doctor">运行自检</button>
      <span class="meta">{{ msg }}</span>
    </div>
  </div>

  <div class="field">
    <label>运行日志</label>
    <div class="logs">{{ logs.join("\n") }}</div>
  </div>
</template>
