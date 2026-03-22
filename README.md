# wechat-agent-channel

把微信消息转给 `Claude Code` 或 `Codex`。

License: MIT

规则很简单：
- 消息里包含 `codex`，走 Codex
- 其他消息，走 Claude Code

## 依赖

- Node.js 18+
- `@anthropic-ai/claude-code`
- `@openai/codex`
- 微信 ClawBot 的 `BOT_TOKEN`

安装 CLI：

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
```

安装项目依赖：

```bash
npm install
```

## 首次登录

```bash
claude
codex
```

## 配置

Windows:

```cmd
set BOT_TOKEN=你的token
```

macOS / Linux:

```bash
export BOT_TOKEN=你的token
```

## 启动

在项目目录运行：

```bash
claude --dangerously-load-development-channels server:wechat
```

Claude Code 会读取 [.mcp.json](/e:/play/wechat-agent-channel/.mcp.json)，启动这个项目并开始监听微信消息。

## 使用

示例：

- `帮我解释这段代码` -> Claude Code
- `codex 帮我写个脚本` -> Codex
- `codex 刚才那个继续改` -> 继续同一个 Codex 会话

## 说明

- Claude Code 走 MCP channel
- Codex 走 `codex app-server`
- Codex 会话映射保存在 [sessions/codex-threads.json](/e:/play/wechat-agent-channel/sessions/codex-threads.json)
- 回复会截断到 1000 字以内

## 主要文件

- [index.js](/e:/play/wechat-agent-channel/index.js): 主入口
- [router.js](/e:/play/wechat-agent-channel/router.js): 路由规则
- [wechat.js](/e:/play/wechat-agent-channel/wechat.js): 微信 API
- [sessions/codex-session.js](/e:/play/wechat-agent-channel/sessions/codex-session.js): Codex 会话管理
