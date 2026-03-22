# wechat-agent-channel

把微信消息转给 `Claude Code` 或 `Codex`。

License: MIT

## 获取项目

GitHub:

```bash
git clone https://github.com/sitarua/wechat-agent-channel.git
cd wechat-agent-channel
```

Gitee:

```bash
git clone https://gitee.com/zywoo121/wechat-agent-channel.git
cd wechat-agent-channel
```

规则很简单：
- 消息里包含 `codex`，走 Codex
- 其他消息，走 Claude Code

## 依赖

- Node.js 18+
- `@anthropic-ai/claude-code`
- `@openai/codex`
- 微信 iOS 版 ClawBot

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
npm run setup
```

`npm run setup` 会显示二维码，用微信扫码并确认后，微信登录凭据会自动保存到本地。

默认凭据位置：

```text
~/.wechat-agent-channel/wechat/account.json
```

## 可选配置

如果你想手动覆盖登录凭据，也支持环境变量：

- `BOT_TOKEN`
- `WECHAT_BASE_URL`

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

- 微信默认使用本地保存的登录凭据；如果设置了 `BOT_TOKEN`，则优先使用环境变量
- 微信消息通过 `ilink/bot/getupdates` 长轮询接收，不是 WebSocket
- Claude Code 走 MCP channel
- Codex 走 `codex app-server`
- Codex 会话映射保存在 [sessions/codex-threads.json](/e:/play/wechat-agent-channel/sessions/codex-threads.json)
- 回复会截断到 1000 字以内

## 主要文件

- [index.js](/e:/play/wechat-agent-channel/index.js): 主入口
- [router.js](/e:/play/wechat-agent-channel/router.js): 路由规则
- [wechat.js](/e:/play/wechat-agent-channel/wechat.js): 微信 API
- [sessions/codex-session.js](/e:/play/wechat-agent-channel/sessions/codex-session.js): Codex 会话管理
