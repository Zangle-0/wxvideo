<script setup lang="ts">
import { computed, ref } from "vue";
import { api, type Video } from "../api";

const props = defineProps<{
  video: Video;
  progress?: { bytes: number; total: number };
  status?: string;
  active?: boolean;
  badge?: string;
}>();

const chosen = ref(""); // "" = 最佳画质（默认）

interface Spec { fmt: string; w?: number; h?: number; br?: number; codec?: string }

const specs = computed<Spec[]>(() => {
  try {
    return (JSON.parse(props.video.specs_json || "[]") as Spec[]).filter((s) => s && s.fmt);
  } catch {
    return [];
  }
});

const pixel = (s: Spec) => (s.w || 0) * (s.h || 0);

const bestFmt = computed(() => {
  if (!specs.value.length) return "";
  const s = [...specs.value].sort((a, b) => pixel(b) - pixel(a) || (b.br || 0) - (a.br || 0));
  return s[0].fmt;
});

const smallFmt = computed(() => {
  if (specs.value.length < 2) return "";
  const s = [...specs.value].sort((a, b) => pixel(a) - pixel(b) || (a.br || 0) - (b.br || 0));
  return s[0].fmt === bestFmt.value ? "" : s[0].fmt;
});

const pct = computed(() => {
  const p = props.progress;
  if (!p || !p.total) return 0;
  return Math.min(100, Math.round((p.bytes / p.total) * 100));
});

function human(ms: number) {
  if (!ms) return "";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

async function download() {
  await api.download(props.video.object_id, chosen.value || bestFmt.value || undefined);
}
</script>

<template>
  <div class="card" :class="{ active }">
    <div class="cover" :style="video.cover_url ? { backgroundImage: `url(${video.cover_url})` } : {}">
      <span v-if="badge" class="badge live">● {{ badge }}</span>
      <span v-if="video.duration_ms" class="badge">{{ human(video.duration_ms) }}</span>
    </div>
    <div class="body">
      <div class="title">{{ video.title || video.object_id }}</div>
      <div class="meta">
        <span>{{ video.author || "未知作者" }}</span>
        <span v-if="video.file_size">{{ (video.file_size / 1048576).toFixed(1) }} MB</span>
      </div>

      <div class="row">
        <select v-if="smallFmt" v-model="chosen">
          <option value="">最佳画质</option>
          <option :value="smallFmt">省流</option>
        </select>
        <button class="btn primary" :disabled="status === 'downloading'" @click="download">
          {{ status === "downloading" ? "下载中…" : "下载" }}
        </button>
      </div>

      <div v-if="status === 'downloading' || (progress && progress.total)" class="progress">
        <i :style="{ width: pct + '%' }" />
      </div>
      <div v-if="status === 'done'" class="meta">已保存到下载目录</div>
    </div>
  </div>
</template>
