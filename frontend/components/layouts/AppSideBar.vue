<script setup lang="ts">
import type MenuItem from "~/types/MenuItem";
import SideBarMenu from "./SideBarMenu.vue";

const route = useRoute();
const currentPath = computed(() => route.path);

// TODO make this a store
const servers = reactive([
  {
    id: "vanilla",
  },
  {
    id: "creative",
  },
  {
    id: "fc4",
  },
]);

const collapsed = ref(false);

const menuItems = computed<MenuItem[]>(() => {
  return [
    {
      title: "首页",
      icon: "HomeFilled",
      path: "/",
    },
    {
      title: "服务器列表",
      icon: "Coin",
      path: "/servers",
    },
    {
      title: "服务器管理",
      icon: "Operation",
      items: servers.map((server) => ({
        title: server.id,
        icon: "Monitor",
        path: `/server/${server.id}`,
      })),
    },
  ];
});
</script>

<template>
  <div
    class="sidebar-container flex flex-col h-full border-r-2 border-gray-100"
  >
    <ElScrollbar class="sidebar flex-1 flex-shrink-0" view-class="h-full">
      <ElMenu
        class="!p-2 !border-r-0"
        :collapse="collapsed"
        :router="true"
        :default-active="currentPath"
      >
        <SideBarMenu :items="menuItems" />
      </ElMenu>
    </ElScrollbar>
    <div
      class="flex items-center px-2 h-12 border-t-2 cursor-pointer"
      @click="collapsed = !collapsed"
    >
      <div class="collapse-button" v-if="collapsed">
        <ElIcon class="flex items-center" :size="20">
          <ElIconExpand></ElIconExpand>
        </ElIcon>
      </div>
      <div class="collapse-button w-full" v-else>
        <ElIcon :size="20" class="mr-2">
          <ElIconFold></ElIconFold>
        </ElIcon>
        <span class="text-base">折叠</span>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.collapse-button {
  @apply flex items-center p-2 rounded-md;
}

.collapse-button:hover {
  background-color: var(--el-menu-hover-bg-color);
}
</style>
