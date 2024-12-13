<script setup lang="ts">
import { Coin, HomeFilled, Monitor, Operation } from "@element-plus/icons-vue";
import type MenuItem from "~/types/MenuItem";

// depth is used to calculate the left margin of the menu items
const { items, depth = 0 } = defineProps<{
  items: MenuItem[];
  depth?: number;
}>();

const leftMarginStyleValue = computed(() => {
  return `${depth / 2}rem`;
});

const leftMarginStyle = computed(() => {
  return {
    marginLeft: leftMarginStyleValue.value,
  };
});

const stringToComponent = (name: string) => {
  switch (name) {
    case "Coin":
      return Coin;
    case "HomeFilled":
      return HomeFilled;
    case "Monitor":
      return Monitor;
    case "Operation":
      return Operation;
    default:
      return null;
  }
};
</script>
<template>
  <template v-for="item in items">
    <ElSubMenu
      v-if="item.items"
      :index="item.path || item.title"
      class="sub-menu"
    >
      <template #title>
        <ElIcon v-if="item.icon" class="!mr-2 !w-5" :size="20">
          <component :is="stringToComponent(item.icon)"></component>
        </ElIcon>
        <span class="text-base">{{ item.title }}</span>
      </template>
      <SideBarMenu :items="item.items" :depth="depth + 1" />
    </ElSubMenu>
    <ElMenuItem
      v-else
      :index="item.path"
      class="menu-item rounded-md !h-10 !pl-2"
      :style="leftMarginStyle"
    >
      <ElIcon v-if="item.icon" class="!mr-2 !w-5" :size="20">
        <component :is="stringToComponent(item.icon)"></component>
      </ElIcon>
      <span class="text-base">{{ item.title }}</span>
    </ElMenuItem>
  </template>
</template>

<style lang="scss" scoped>
// a bit hacky, but works
.sub-menu > :deep(div) {
  margin-left: v-bind(leftMarginStyleValue);
  @apply rounded-md !h-10 !pl-2;
}
</style>
