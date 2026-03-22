/**
 * 路由规则
 * - 默认：走 Claude Code（MCP 原生 session，有状态）
 * - 包含 "codex" 关键词：走 Codex（本地 session 管理器，有状态）
 * - 发送 "/clear" 可以清除当前用户在 Codex 的对话历史（可扩展）
 */
export function routeTask(text) {
  const lower = text.toLowerCase();

  if (lower.includes("codex") || lower.startsWith("/codex")) {
    return "codex";
  }

  return "claude";
}
