// Mirrors MCServerInfo from minecraft-docker-manager-lib.
export interface ServerInfo {
  id: string;
  name: string;
  path: string;
  javaVersion: number;
  maxMemoryBytes: number;
  serverType: ServerType;
  gameVersion: string;
  gamePort: number;
  rconPort: number;
}

export type ServerType =
  | "VANILLA"
  | "PAPER"
  | "FORGE"
  | "NEOFORGE"
  | "FABRIC"
  | "SPIGOT"
  | "BUKKIT"
  | "CUSTOM";

export type ServerStatus =
  | "REMOVED"
  | "EXISTS"
  | "CREATED"
  | "RUNNING"
  | "STARTING"
  | "HEALTHY";
