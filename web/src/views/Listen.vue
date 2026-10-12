<script setup lang="ts">
import { ref } from "vue";
import VideoCard from "../components/VideoCard.vue";
import { api, type Video } from "../api";

defineProps<{
  videos: Video[];
  mode: "played" | "all";
  target: any;
  progress: Record<string, { bytes: number; total: number }>;
  dlStatus: Record<string, string>;
}>();
const emit = defineEmits<{
  (e: "refresh"): void;
  (e: "mode", m: "played" | "all"): void;
}>();

const link = ref("");

async function setTarget() {
  const url = link.value.trim();
  if (!url) return;
  navigator.clipboard?.writeText(url).catch(() => {});
  await api.target(url);
}

function badgeOf(v: Video, i: number) {
  if (v.target) return "链接目标";
  if (v.focused) return "当前查看";
  if (i === 0 && v.last_played_at) return "最近播放";
  return "";
}
</script>

<template>
  <div class="card" style="margin-bottom: 16px">
    <div class="body">
      <div class="meta">要下某一条分享链接？粘贴链接 → 点「定位」→ 按提示在微信打开</div>
      <div class="row">
        <input class="input" style="flex:1" v-model="link" placeholder="https://weixin.qq.com/sph/xxxx" />
        <button class="btn primary" @click="setTarget">定位这条链接</button>
      </div>
      <div v-if="target && target.object_id" class="meta" style="color: var(--ok)">
        ✅ 已锁定：{{ target.author }} ·《{{ target.title }}》 —— 请在下方点它的「下载」
      </div>
      <div v-else-if="target && target.title" class="meta">
        拿到了预览（{{ target.author }} · {{ target.title.slice(0, 20) }}），但列表里还没匹配到，稍等或刷新。
      </div>
      <div v-else-if="target" class="meta" style="color: var(--accent)">
        已记下这条链接。请在**微信里打开它**（发到「文件传输助手」再点最稳），页面加载后会自动锁定。
      </div>
    </div>
  </div>

  <div class="row" style="margin-bottom: 14px">
    <button class="btn" :class="{ primary: mode === 'played' }" @click="emit('mode', 'played')">
      本次播放过
    </button>
    <button class="btn" :class="{ primary: mode === 'all' }" @click="emit('mode', 'all')">
      全部历史
    </button>
    <span class="meta">{{ videos.length }} 条</span>
  </div>

  <div v-if="!videos.length" class="empty">
    <template v-if="mode === 'played'">
      还没有播放记录。<br />
      在视频号里**播放**一个视频，它会出现在这里（按最近播放排序，最上面就是你正在看的）。<br />
      想看整页加载的其它视频，切到「全部历史」。
    </template>
    <template v-else>
      暂无历史。开启监听并浏览/播放视频后会记录在这里。
    </template>
  </div>

  <div v-else class="grid">
    <VideoCard
      v-for="(v, i) in videos"
      :key="v.object_id"
      :video="v"
      :progress="progress[v.object_id]"
      :status="dlStatus[v.object_id]"
      :active="!!(v.target || v.focused)"
      :badge="badgeOf(v, i)"
      @refresh="emit('refresh')"
    />
  </div>
</template>
