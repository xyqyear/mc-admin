<script setup lang="ts">
import { defineProps } from "vue";
import TagIconWithTooltip from "./TagIconWithTooltip.vue";

const { state } = defineProps<{
  state: "running" | "paused" | "stopped" | "down";
}>();
</script>

<template>
  <TagIconWithTooltip
    tag-type="success"
    v-if="state === 'running'"
    icon="material-symbols:play-circle-outline"
  >
    运行中
  </TagIconWithTooltip>

  <TagIconWithTooltip
    tag-type="warning"
    v-else-if="state === 'paused'"
    icon="material-symbols:pause-circle-outline"
  >
    暂停
  </TagIconWithTooltip>

  <TagIconWithTooltip
    tag-type="danger"
    v-else-if="state === 'stopped'"
    icon="material-symbols:stop-circle-outline"
  >
    停止
  </TagIconWithTooltip>

  <TagIconWithTooltip
    tag-type="info"
    v-else-if="state === 'down'"
    icon="material-symbols:build-circle-outline"
  >
    未创建
  </TagIconWithTooltip>
</template>
