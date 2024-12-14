<script setup lang="ts">
const route = useRoute();

const serverId = computed(() => route.params.id);
</script>

<template>
  <div class="flex justify-center items-center">{{ serverId }}</div>
</template>
