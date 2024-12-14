<script setup lang="ts">
import type MenuItem from "~/types/MenuItem";

// depth is used to calculate the left margin of the menu items
const { items } = defineProps<{
  items: MenuItem[];
}>();
</script>
<template>
  <template v-for="item in items">
    <ElSubMenu
      v-if="item.items"
      :index="item.path || item.title"
      class="sub-menu"
    >
      <template #title>
        <ElIcon v-if="item.icon" size="20">
          <NuxtIcon :name="item.icon" />
        </ElIcon>
        <span class="text-base">{{ item.title }}</span>
      </template>
      <SideBarMenu :items="item.items" />
    </ElSubMenu>
    <ElMenuItem v-else :index="item.path" class="menu-item rounded-md">
      <ElIcon v-if="item.icon" size="20">
        <NuxtIcon :name="item.icon" />
      </ElIcon>
      <span class="text-base">{{ item.title }}</span>
    </ElMenuItem>
  </template>
</template>

<style lang="scss" scoped>
// a bit hacky, but works
.sub-menu > :deep(div) {
  @apply rounded-md;
}
</style>
