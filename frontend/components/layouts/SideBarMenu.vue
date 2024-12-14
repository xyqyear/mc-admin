<script setup lang="ts">
import {
  Coin,
  Filter,
  Folder,
  HomeFilled,
  Monitor,
  Operation,
  Plus,
  RefreshLeft,
  Setting,
  User,
  View,
} from "@element-plus/icons-vue";
import type MenuItem from "~/types/MenuItem";

// depth is used to calculate the left margin of the menu items
const { items } = defineProps<{
  items: MenuItem[];
}>();

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
    case "View":
      return View;
    case "RefreshLeft":
      return RefreshLeft;
    case "Plus":
      return Plus;
    case "User":
      return User;
    case "Setting":
      return Setting;
    case "Folder":
      return Folder;
    case "Filter":
      return Filter;
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
        <ElIcon v-if="item.icon">
          <component :is="stringToComponent(item.icon)"></component>
        </ElIcon>
        <span class="text-base">{{ item.title }}</span>
      </template>
      <SideBarMenu :items="item.items" />
    </ElSubMenu>
    <ElMenuItem v-else :index="item.path" class="menu-item rounded-md">
      <ElIcon v-if="item.icon">
        <component :is="stringToComponent(item.icon)"></component>
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
