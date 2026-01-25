const STORAGE_KEY_PREFIX = 'mc-admin-command-history-';
const MAX_HISTORY_SIZE = 100;

export interface CommandHistory {
  getHistory: (serverId: string) => string[];
  addCommand: (serverId: string, command: string) => void;
  clearHistory: (serverId: string) => void;
}

export const commandHistory: CommandHistory = {
  getHistory: (serverId: string): string[] => {
    const key = STORAGE_KEY_PREFIX + serverId;
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : [];
  },

  addCommand: (serverId: string, command: string): void => {
    const key = STORAGE_KEY_PREFIX + serverId;
    const history = commandHistory.getHistory(serverId);

    // Don't add duplicates of the last command
    if (history.length > 0 && history[history.length - 1] === command) {
      return;
    }

    history.push(command);

    // Limit history size
    if (history.length > MAX_HISTORY_SIZE) {
      history.shift();
    }

    localStorage.setItem(key, JSON.stringify(history));
  },

  clearHistory: (serverId: string): void => {
    const key = STORAGE_KEY_PREFIX + serverId;
    localStorage.removeItem(key);
  }
};
