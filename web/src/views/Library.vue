<script setup lang="ts">
import type { Video } from "../api";

defineProps<{ videos: Video[]; dlStatus: Record<string, string> }>();

function human(ms: number) {
  if (!ms) return "-";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
</script>

<template>
  <div v-if="!videos.length" class="empty">暂无历史。开启监听并播放视频后会记录在这里。</div>
  <table v-else class="table">
    <thead>
      <tr><th>作者</th><th>标题</th><th>时长</th><th>大小</th><th>状态</th></tr>
    </thead>
    <tbody>
      <tr v-for="v in videos" :key="v.object_id">
        <td>{{ v.author || "-" }}</td>
        <td>{{ v.title || v.object_id }}</td>
        <td>{{ human(v.duration_ms) }}</td>
        <td>{{ v.file_size ? (v.file_size / 1048576).toFixed(1) + " MB" : "-" }}</td>
        <td>{{ dlStatus[v.object_id] || "未下载" }}</td>
      </tr>
    </tbody>
  </table>
</template>
