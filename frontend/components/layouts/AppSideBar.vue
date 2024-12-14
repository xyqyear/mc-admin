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
const collapseButtonVisible = ref(true);
const collapseButtonStyle = computed(() => {
  return {
    display: collapseButtonVisible.value ? "block" : "none",
  };
});
const onToggleCollapse = () => {
  collapsed.value = !collapsed.value;
  // when expand, wait for the animation to finish before showing the text
  if (!collapsed.value) {
    setTimeout(() => {
      collapseButtonVisible.value = true;
    }, 300);
  } else {
    collapseButtonVisible.value = false;
  }
};

const menuItems = computed<MenuItem[]>(() => {
  return [
    {
      title: "首页",
      icon: "material-symbols:home",
      path: "/",
    },
    {
      title: "服务器总览",
      icon: "material-symbols:dashboard",
      path: "/overview",
    },
    {
      title: "服务器管理",
      icon: "material-symbols:stacks",
      items: servers
        .map(
          (server): MenuItem => ({
            title: server.id,
            icon: "material-symbols:host",
            items: [
              {
                title: "概览",
                icon: "material-symbols:speed",
                path: `/server/${server.id}`,
              },
              {
                title: "玩家列表",
                icon: "material-symbols:person",
                path: `/server/${server.id}/players`,
              },
              {
                title: "设置",
                icon: "material-symbols:settings",
                path: `/server/${server.id}/compose`,
              },
              {
                title: "文件",
                icon: "material-symbols:folder",
                path: `/server/${server.id}/files`,
              },
              {
                title: "白名单",
                icon: "material-symbols:shield",
                path: `/server/${server.id}/whitelist`,
              },
            ],
          })
        )
        .concat([
          {
            title: "新建",
            icon: "material-symbols:add",
            path: "/server/new",
          },
        ]),
    },
    {
      title: "备份管理",
      icon: "material-symbols:settings-backup-restore",
      path: "/backups",
    },
  ];
});
</script>

<template>
  <div
    class="sidebar-container flex flex-col h-full border-r-2 border-gray-100"
  >
    <ElScrollbar class="sidebar flex-1 flex-shrink-0 p-2" view-class="h-full">
      <ElMenu
        class="menu !border-r-0"
        :collapse="collapsed"
        :router="true"
        :default-active="currentPath"
        :unique-opened="true"
      >
        <SideBarMenu :items="menuItems" />
      </ElMenu>
    </ElScrollbar>
    <div
      class="flex items-center px-3 h-12 border-t-2 cursor-pointer"
      @click="onToggleCollapse"
    >
      <div class="collapse-button w-full flex items-center p-2 rounded-md">
        <ElIcon class="flex items-center" v-if="collapsed" :size="20">
          <NuxtIcon name="material-symbols:left-panel-open" />
        </ElIcon>
        <ElIcon class="flex items-center" v-else :size="20">
          <NuxtIcon name="material-symbols:left-panel-close" />
        </ElIcon>
        <span class="text-base ml-2" :style="collapseButtonStyle">折叠</span>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.collapse-button:hover {
  background-color: var(--el-menu-hover-bg-color);
}

.menu {
  --el-menu-base-level-padding: 0.5rem;
  --el-menu-item-height: 2.5rem;
  --el-menu-sub-item-height: 2.5rem;
  --el-menu-level-padding: 0.5rem;
}
</style>
