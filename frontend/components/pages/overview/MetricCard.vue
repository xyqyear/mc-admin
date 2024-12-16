<script setup lang="ts">
import { type ProgressFn } from "element-plus";

interface Props {
  value: number;
  title: string;
  extraValues?: string;
  isProgress?: boolean;
}

const {
  value,
  title,
  extraValues = "",
  isProgress = false,
} = defineProps<Props>();

const progressBarColors = [
  { color: "#f56c6c", percentage: 100 },
  { color: "#e6a23c", percentage: 80 },
  { color: "#5cb87a", percentage: 60 },
  { color: "#1989fa", percentage: 40 },
  { color: "#6f7ad3", percentage: 20 },
];

const progressBarPercentageFormatter: ProgressFn = (percentage: number) => {
  return percentage.toFixed(2) + "%";
};
</script>

<template>
  <ElCard class="metric-item flex-1">
    <div class="flex flex-col items-center">
      <div v-if="isProgress">
        <ElProgress
          type="dashboard"
          :percentage="value"
          :format="progressBarPercentageFormatter"
          :color="progressBarColors"
        />
      </div>
      <div v-else class="metric-value h-36 flex justify-center items-center">
        <p class="text-2xl font-bold">{{ value }}</p>
      </div>
      <div class="metric-title text-lg font-bold">{{ title }}</div>
      <div v-if="extraValues" class="metric-value">
        {{ extraValues }}
      </div>
    </div>
  </ElCard>
</template>

<style lang="scss" scoped></style>
