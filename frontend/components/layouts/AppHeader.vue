<script setup lang="ts">
import { useTokenStore } from "~/stores/useTokenStore";

const { clearToken } = useTokenStore();

const logout = () => {
  clearToken();
  navigateTo("/login");
};
</script>

<template>
  <div class="h-10 flex items-center">
    <div class="empty-bar flex-1"></div>
    <div
      class="logout-icon flex justify-center items-center mr-2 p-1 rounded-md cursor-pointer"
      @click="logout"
    >
      <ElIcon class="flex items-center" :size="20">
        <NuxtIcon name="material-symbols:logout" />
      </ElIcon>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.logout-icon:hover {
  background-color: var(--el-menu-hover-bg-color);
}
</style>
