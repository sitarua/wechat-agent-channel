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

规则现在改成：
- 首次初始化时，在终端里选择默认 provider：`Codex` 或 `Claude Code`
- 之后微信消息默认都走这个 provider
- 不需要在聊天内容里写 `codex xxx` 这类前缀

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

`npm run setup` 会显示二维码，用微信扫码并确认后保存微信登录凭据。

首次初始化时，`npm run setup` 还会在终端里提示你选择默认 provider：

- `1` -> `Codex`
- `2` -> `Claude Code`

默认凭据位置：

```text
~/.wechat-agent-channel/wechat/account.json
```

默认 provider 配置位置：

```text
~/.wechat-agent-channel/config.json
```

## 可选配置

如果你想手动覆盖登录凭据，也支持环境变量：

- `BOT_TOKEN`
- `WECHAT_BASE_URL`

## 启动

如果默认 provider 选的是 `Codex`，直接在项目目录运行：

```bash
npm start
```

这会直接启动 [index.js](/e:/play/wechat-agent-channel/index.js)，开始监听微信消息，并在内部调用 `codex app-server` 处理会话。
`codex app-server` 不是启动时常驻拉起，而是等微信真正收到消息、并且路由到 Codex 时才懒启动。
Codex 模式下只保留一个 `npm start` 实例；重复启动会被单实例锁拦住，避免多个轮询器同时拉起多个 Codex 会话。

如果默认 provider 选的是 `Claude Code`，在项目目录运行：

```bash
claude --dangerously-load-development-channels server:wechat
```

Claude Code 会读取 [.mcp.json](/e:/play/wechat-agent-channel/.mcp.json)，启动这个项目并开始监听微信消息。

## 使用

示例：

- 如果初始化时选择了 `Codex`，那么 `帮我写个脚本` 会直接走 Codex
- 如果初始化时选择了 `Claude Code`，那么 `帮我解释这段代码` 会直接走 Claude Code

## 说明

- 微信默认使用本地保存的登录凭据；如果设置了 `BOT_TOKEN`，则优先使用环境变量
- 微信消息通过 `ilink/bot/getupdates` 长轮询接收，不是 WebSocket
- Claude Code 走 MCP channel
- Codex 走 `codex app-server`
- 默认 provider 通过本地配置或环境变量 `WECHAT_AGENT_PROVIDER` 控制
- Codex 会话映射保存在 [sessions/codex-threads.json](/e:/play/wechat-agent-channel/sessions/codex-threads.json)
- 回复会截断到 1000 字以内

## 主要文件

- [index.js](/e:/play/wechat-agent-channel/index.js): 主入口
- [router.js](/e:/play/wechat-agent-channel/router.js): 路由规则
- [wechat.js](/e:/play/wechat-agent-channel/wechat.js): 微信 API
- [sessions/codex-session.js](/e:/play/wechat-agent-channel/sessions/codex-session.js): Codex 会话管理
