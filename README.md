<a id="top"></a>

# wechat-agent-channel

[简体中文](#zh-cn) | [English](#en)

---

<a id="zh-cn"></a>

## 简体中文

把微信消息接到本地 AI 编码助手里用。支持 `Codex`、`OpenCode`、`Claude Code`。

### 先准备好

- Python 3.11+
- Node.js 18+
- 微信端已接入 ClawBot
- 你要用的 CLI 已安装，并且终端里能直接运行

常见安装：

```bash
npm install -g @openai/codex
npm install -g opencode-ai
npm install -g @anthropic-ai/claude-code
```

安装项目依赖：

```bash
npm install
```

### 用 Codex / OpenCode

1. 先确认命令能跑：

```bash
codex
opencode
```

2. 选择默认 provider：

```bash
npm run setup
```

3. 启动：

```bash
npm start
```

如果你想重新选择默认 provider：

```bash
npm run setup:reset
```

### 用 Claude Code

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

### 微信里怎么用

启动后，直接给 ClawBot 发消息就行。

示例：

- `帮我写个 Python 脚本`
- `解释一下这个项目怎么启动`
- `帮我看看这个报错是什么意思`

如果你已经选了默认 provider，就不用再写前缀。

### 会话命令

- `/new` 或 `新任务`
- `/new 重构支付`
- `/list` 或 `会话列表`
- `/current` 或 `当前会话`
- `/switch 2` 或 `切换会话 2`

### 常用环境变量

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_AGENT_PROVIDER`
- `OPENCODE_MODEL`
- `OPENCODE_TURN_TIMEOUT_MS`
- `OPENCODE_THINKING`
- `OPENCODE_BIN`

### 说明

- `Codex` 和 `OpenCode` 走本地 CLI
- `Claude Code` 走独立 MCP 插件模式
- `OpenCode` 在微信里默认只返回最终回答；如需保留 thinking，可设置 `OPENCODE_THINKING=1`
- 微信登录凭据默认保存在用户目录下
- 同一时间建议只保留一个运行中的实例

[回到顶部](#top)

---

<a id="en"></a>

## English

Use WeChat as a front end for local coding agents. Supports `Codex`, `OpenCode`, and `Claude Code`.

### Prerequisites

- Python 3.11+
- Node.js 18+
- A WeChat client connected to ClawBot
- The CLI you want to use is installed and available in `PATH`

Common installs:

```bash
npm install -g @openai/codex
npm install -g opencode-ai
npm install -g @anthropic-ai/claude-code
```

Install project dependencies:

```bash
npm install
```

### Codex / OpenCode

1. Make sure the commands work:

```bash
codex
opencode
```

2. Choose the default provider:

```bash
npm run setup
```

3. Start the bridge:

```bash
npm start
```

To choose again:

```bash
npm run setup:reset
```

### Claude Code

1. Sign in with WeChat:

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

### How to use

After startup, send messages to ClawBot in WeChat.

Examples:

- `Write a Python script for me`
- `Explain how this project starts`
- `What does this error mean?`

If you already chose a default provider, you do not need to add a prefix.

### Session Commands

- `/new` or `新任务`
- `/new payment-refactor`
- `/list` or `会话列表`
- `/current` or `当前会话`
- `/switch 2` or `切换会话 2`

### Common environment variables

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_AGENT_PROVIDER`
- `OPENCODE_MODEL`
- `OPENCODE_TURN_TIMEOUT_MS`
- `OPENCODE_THINKING`
- `OPENCODE_BIN`

### Notes

- `Codex` and `OpenCode` run through local CLIs
- `Claude Code` uses a separate MCP plugin flow
- `OpenCode` returns the final answer by default in WeChat; set `OPENCODE_THINKING=1` if you want thinking enabled
- WeChat credentials are stored in your user directory by default
- It is best to keep only one running instance at a time

[Back to top](#top)

---

License: MIT
