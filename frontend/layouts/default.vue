<script setup lang="ts">
import AppHeader from "~/components/layouts/AppHeader.vue";
import AppSideBar from "~/components/layouts/AppSideBar.vue";
</script>

<template>
  <div class="page h-screen flex flex-col">
    <div class="header border-b-2 border-gray-100">
      <AppHeader />
    </div>
    <div class="bottom flex-1 flex flex-row overflow-y-hidden">
      <AppSideBar />
      <!-- can be replaced with a div with overflow-y-auto -->
      <!-- it's just that ElScrollbar's scrollbar is prettier -->
      <ElScrollbar class="content flex-1 p-4" view-class="h-full">
        <slot />
      </ElScrollbar>
    </div>
  </div>
</template>
