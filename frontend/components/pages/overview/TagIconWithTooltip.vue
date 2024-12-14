<script setup lang="ts">
const { tagType = "success", icon = "material-symbols:question-mark" } =
  defineProps<{
    tagType?: "success" | "warning" | "danger" | "info";
    icon?: string;
  }>();
</script>

<template>
  <ElTooltip trigger="hover" placement="right" effect="light">
    <ElTag :type="tagType" class="tag !px-1">
      <ElIcon class="icon">
        <NuxtIcon :name="icon" class="cursor-auto" />
      </ElIcon>
    </ElTag>
    <template #content> <slot /> </template>
  </ElTooltip>
</template>

<style lang="scss" scoped>
.tag > :deep(span) {
  @apply flex items-center;
}

.icon {
  --el-icon-size: 20px;
}
</style>
