<a id="top"></a>

# wechat-agent-channel

[简体中文](#zh-cn) | [English](#en)

---

<a id="zh-cn"></a>

## 简体中文

把微信消息接到本地 AI 编码助手里用。你可以选择把消息转给 `Codex`、`OpenCode` 或 `Claude Code`，然后直接在微信里和它们对话。

### 运行前准备

- Python 3.11+
- Node.js 18+
- 微信端已接入 ClawBot
- 你要使用的 CLI 已安装并能在终端里直接运行

示例：

```bash
npm install -g @openai/codex
# 按 OpenCode 官方文档安装 opencode
npm install -g @anthropic-ai/claude-code
```

安装项目依赖：

```bash
npm install
```

项目会自动探测可用的 Python 解释器：

- macOS / Linux：优先 `python3`，其次 `python`
- Windows：优先 `py -3`，其次 `python`

### Codex / OpenCode

先确认 CLI 能正常启动：

```bash
codex
opencode
```

初始化：

```bash
npm run setup
```

这条路径只给 `Codex` / `OpenCode` 选择默认 provider。  
如果你想重新选择一次：

```bash
npm run setup:reset
```

启动：

```bash
npm start
```

### Claude Plugin Mode

这条路径单独给 `Claude Code` 用，不走主应用的 provider 路由。

1. 微信扫码登录：

```bash
npm run claude:setup
```

2. 生成或更新 `.mcp.json`：

```bash
npm run claude:install
```

3. 启动 Claude Code：

```bash
claude --dangerously-load-development-channels server:wechat
```

如果你之前已经试过旧版本，先把 Claude Code 会话完全退出再重开。  
启动后可以用下面这条命令确认 MCP 已连上：

```bash
claude mcp list
```

如果之前拒绝过项目里的 `wechat` MCP server，先运行：

```bash
claude mcp reset-project-choices
```

### 怎么用

启动后，直接在微信里给 ClawBot 发消息即可。

示例：

- `帮我写个 Python 脚本`
- `解释一下这个项目怎么启动`
- `帮我看看这个报错是什么意思`

如果你在初始化时已经选了默认 provider，就不需要在消息里额外写前缀。

### 会话命令

同一个微信用户默认会续接当前会话。你也可以像 `cc-connect` 一样直接在微信里管理会话：

- `/new` 或 `新任务`：创建并切换到一个新会话
- `/new 重构支付` 或 `新建会话 重构支付`：创建带名字的新会话
- `/list` 或 `会话列表`：查看当前用户的会话列表
- `/current` 或 `当前会话`：查看当前正在使用的会话
- `/switch 2` 或 `切换会话 2`：切换到某个会话

这些中文命令会在内部转成对应的英文语义，不会被发送给 provider。

### 可选环境变量

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_AGENT_PROVIDER`

### 说明

- `Codex` 和 `OpenCode` 都是本地 CLI 方式运行
- `Claude Code` 走独立的 MCP 插件模式
- 微信登录凭据默认保存在用户目录下
- 同一时间只建议保留一个运行中的实例
- 会话命令设计参考了 [chenhg5/cc-connect](https://github.com/chenhg5/cc-connect) 提供的部分思路

[回到顶部](#top)

---

<a id="en"></a>

## English

Use WeChat as a front end for local coding agents. You can route messages to `Codex`, `OpenCode`, or `Claude Code` and talk to them directly from WeChat.

### Requirements

- Python 3.11+
- Node.js 18+
- A WeChat client connected to ClawBot
- The CLI for the provider you want to use must be installed and available in `PATH`

Examples:

```bash
npm install -g @openai/codex
# Install opencode from the official docs
npm install -g @anthropic-ai/claude-code
```

Install project dependencies:

```bash
npm install
```

The project auto-detects a working Python interpreter:

- macOS / Linux: prefer `python3`, then `python`
- Windows: prefer `py -3`, then `python`

### Codex / OpenCode

Make sure the CLIs can start:

```bash
codex
opencode
```

Then run:

```bash
npm run setup
```

This path only manages the default provider for `Codex` / `OpenCode`.  
To choose again:

```bash
npm run setup:reset
```

```bash
npm start
```

### Claude Plugin Mode

This path is only for `Claude Code` and does not use the main provider router.

1. WeChat QR login:

```bash
npm run claude:setup
```

2. Create or update `.mcp.json`:

```bash
npm run claude:install
```

3. Start Claude Code:

```bash
claude --dangerously-load-development-channels server:wechat
```

If you already tried an older build, fully quit Claude Code before starting again.  
After startup, you can confirm the MCP server is connected with:

```bash
claude mcp list
```

If you previously denied the `wechat` MCP server, run:

```bash
claude mcp reset-project-choices
```

### How to use it

After startup, just send a message to ClawBot in WeChat.

Examples:

- `Write a Python script for me`
- `Explain how this project starts`
- `What does this error mean?`

If you already selected a default provider during setup, you do not need to add any provider prefix in the message.

### Session Commands

Messages from the same WeChat user continue the current session by default. You can also manage sessions directly from WeChat:

- `/new` or `新任务`: create and switch to a new session
- `/new payment-refactor` or `新建会话 payment-refactor`: create a named session
- `/list` or `会话列表`: list sessions for the current user
- `/current` or `当前会话`: show the active session
- `/switch 2` or `切换会话 2`: switch to a session by index or name

The Chinese commands are translated into the matching English intent internally and are not forwarded to the provider.

### Optional environment variables

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_AGENT_PROVIDER`

### Notes

- `Codex` and `OpenCode` run through their local CLIs
- `Claude Code` uses a standalone MCP plugin path
- WeChat credentials are stored in your user directory by default
- It is best to keep only one running instance at a time
- The session command UX was partly inspired by [chenhg5/cc-connect](https://github.com/chenhg5/cc-connect)

[Back to top](#top)

---

License: MIT
