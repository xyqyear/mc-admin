export function restorationBindingMessage(issue: string): string {
  return issue === 'generation_changed'
    ? '此记录属于同名的旧服务器实例，无法回滚到当前实例。'
    : '无法确认此记录对应的服务器实例，请先核对恢复历史；当前禁止回滚。'
}
