<script setup lang="ts">
import MetricCard from "~/components/pages/overview/MetricCard.vue";
import ServerStateTag from "~/components/pages/overview/ServerStateTag.vue";

const systemInfo = ref({
  serverNum: 4,
  onlinePlayerNum: 2,
  cpuPercentage: 10,
  cpuLoad1Min: 1.0,
  cpuLoad5Min: 1.0,
  cpuLoad15Min: 1.0,
  ramUsedGB: 20.0,
  ramTotalGB: 48.0,
  diskUsedGB: 40.0,
  diskTotalGB: 400.0,
  backupUsedGB: 80.0,
  backupTotalGB: 256.0,
});

interface ServerInfo {
  id: string;
  onlinePlayers: string[];
  state: "running" | "paused" | "stopped" | "down";
  diskUsedGB: number;
  port: number;
}

const serversInfo = reactive<ServerInfo[]>([
  {
    id: "vanilla",
    onlinePlayers: ["player1", "player2"],
    state: "running",
    diskUsedGB: 20,
    port: 25565,
  },
  {
    id: "creative",
    onlinePlayers: [],
    state: "paused",
    diskUsedGB: 30,
    port: 25566,
  },
  {
    id: "fc4",
    onlinePlayers: [],
    state: "stopped",
    diskUsedGB: 40,
    port: 25567,
  },
  {
    id: "monifactory",
    onlinePlayers: [],
    state: "down",
    diskUsedGB: 50,
    port: 25568,
  },
]);

const operationAvailable = (operation: string, server: ServerInfo) => {
  switch (operation) {
    case "start":
      return (
        server.state === "stopped" ||
        server.state === "paused" ||
        server.state === "down"
      );
    case "pause":
      return server.state === "running";
    case "stop":
      return server.state === "running" || server.state === "paused";
    case "restart":
      return server.state === "running" || server.state === "paused";
    case "down":
      return (
        server.state === "running" ||
        server.state === "stopped" ||
        server.state === "paused"
      );
    default:
      return false;
  }
};

const operationIconClass = (operation: string, server: ServerInfo) => {
  return operationAvailable(operation, server)
    ? "operation-icon"
    : "operation-icon-disabled";
};
</script>

<template>
  <div class="main-container flex flex-col h-full w-full">
    <div class="metrics-list flex flex-wrap gap-4 mb-4">
      <MetricCard :value="systemInfo.serverNum" title="服务器总数" />
      <MetricCard :value="systemInfo.onlinePlayerNum" title="在线玩家总数" />
      <MetricCard
        :value="systemInfo.cpuPercentage"
        :extra-values="`${systemInfo.cpuLoad1Min.toFixed(
          2
        )}, ${systemInfo.cpuLoad5Min.toFixed(
          2
        )}, ${systemInfo.cpuLoad15Min.toFixed(2)}`"
        title="CPU占用"
        :is-progress="true"
      />
      <MetricCard
        :value="(systemInfo.ramUsedGB / systemInfo.ramTotalGB) * 100"
        :extra-values="`${systemInfo.ramUsedGB}GB / ${systemInfo.ramTotalGB}GB`"
        title="RAM占用"
        :is-progress="true"
      />
      <MetricCard
        :value="(systemInfo.diskUsedGB / systemInfo.diskTotalGB) * 100"
        :extra-values="`${systemInfo.diskUsedGB}GB / ${systemInfo.diskTotalGB}GB`"
        title="硬盘使用"
        :is-progress="true"
      />
      <MetricCard
        :value="(systemInfo.backupUsedGB / systemInfo.backupTotalGB) * 100"
        :extra-values="`${systemInfo.backupUsedGB}GB / ${systemInfo.backupTotalGB}GB`"
        title="备份空间"
        :is-progress="true"
      />
    </div>
    <div class="server-list flex-1">
      <ElCard>
        <ElTable :data="serversInfo" class="w-full h-full">
          <ElTableColumn prop="id" label="服务器" width="120" />
          <ElTableColumn
            prop="port"
            label="端口"
            width="70"
            :formatter="(row: ServerInfo) => row.port.toString()"
          />
          <ElTableColumn label="状态" prop="state" width="60">
            <template #default="scope">
              <ServerStateTag :state="scope.row.state" />
            </template>
          </ElTableColumn>
          <ElTableColumn
            prop="diskUsedGB"
            label="硬盘使用"
            width="80"
            :formatter="(row: ServerInfo) => row.diskUsedGB.toFixed(1) + 'GB'"
          />
          <ElTableColumn
            prop="onlinePlayers"
            label="玩家数量"
            :formatter="(row: ServerInfo) => row.onlinePlayers.length.toString()"
            width="80"
          />
          <ElTableColumn
            prop="onlinePlayers"
            label="在线玩家"
            :formatter="(row: ServerInfo) => row.onlinePlayers.join(', ')"
          />
          <ElTableColumn label="操作" width="240" fixed="right">
            <template #default="scope">
              <ElTooltip content="启动" placement="top" effect="light">
                <ElIcon
                  size="24"
                  :class="operationIconClass('start', scope.row)"
                >
                  <NuxtIcon name="material-symbols:play-arrow"></NuxtIcon>
                </ElIcon>
              </ElTooltip>
              <ElTooltip content="暂停" placement="top" effect="light">
                <ElIcon
                  size="24"
                  :class="operationIconClass('pause', scope.row)"
                >
                  <NuxtIcon name="material-symbols:pause"></NuxtIcon>
                </ElIcon>
              </ElTooltip>
              <ElTooltip content="停止" placement="top" effect="light">
                <ElIcon
                  size="24"
                  :class="operationIconClass('stop', scope.row)"
                >
                  <NuxtIcon name="material-symbols:stop"></NuxtIcon>
                </ElIcon>
              </ElTooltip>
              <ElTooltip content="重启" placement="top" effect="light">
                <ElIcon
                  size="24"
                  :class="operationIconClass('restart', scope.row)"
                >
                  <NuxtIcon name="material-symbols:restart-alt"></NuxtIcon>
                </ElIcon>
              </ElTooltip>
              <ElTooltip content="离线" placement="top" effect="light">
                <ElIcon
                  size="24"
                  :class="operationIconClass('down', scope.row)"
                >
                  <NuxtIcon name="material-symbols:arrow-downward"></NuxtIcon>
                </ElIcon>
              </ElTooltip>
              <ElTooltip content="详情" placement="top" effect="light">
                <ElIcon size="24" class="operation-icon ml-2">
                  <NuxtIcon name="material-symbols:arrow-outward"></NuxtIcon>
                </ElIcon>
              </ElTooltip>
            </template>
          </ElTableColumn>
        </ElTable>
      </ElCard>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.running-state-tag > :deep(span) {
  @apply flex items-center;
}

.server-list :deep(.cell) {
  @apply flex items-center;
}

.operation-icon:hover {
  cursor: pointer;
  color: var(--el-color-primary);
}

.operation-icon:active {
  color: var(--el-color-primary-dark);
}

.operation-icon-disabled {
  cursor: not-allowed;
  color: var(--el-disabled-text-color);
}
</style>
