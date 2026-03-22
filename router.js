const SUPPORTED_PROVIDERS = new Set(["claude", "codex"]);

/**
 * 路由规则
 * - 默认：使用初始化时选定的 provider
 * - 可通过环境变量 / 本地配置切换，不要求在聊天内容里带关键词
 */
export function routeTask(defaultProvider = "claude") {
  const provider = String(defaultProvider || "claude").toLowerCase();
  return SUPPORTED_PROVIDERS.has(provider) ? provider : "claude";
}
