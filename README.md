<a id="top"></a>

# wechat-agent-channel

[简体中文](#zh-cn) | [English](#en)

---

<a id="zh-cn"></a>

## 简体中文

把微信消息接到本地 AI 编码助手里用。你可以选择把消息转给 `Codex`、`OpenCode` 或 `Claude Code`，然后直接在微信里和它们对话。

### 适合做什么

- 在微信里让 AI 帮你看代码、写脚本、解释仓库
- 在外面不方便开 IDE 时，继续和本地编码助手协作
- 在同一套微信入口下切换不同 provider

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

### 首次使用

先确认 CLI 能正常启动：

```bash
codex
opencode
claude
```

然后运行初始化：

```bash
npm run setup
```

初始化会做两件事：

- 显示微信登录二维码，扫码后保存凭据
- 让你选择默认 provider

可选项：

- `1` -> `Codex`
- `2` -> `OpenCode`
- `3` -> `Claude Code`

### 怎么启动

如果默认 provider 是 `Codex` 或 `OpenCode`：

```bash
npm start
```

如果默认 provider 是 `Claude Code`：

```bash
claude --dangerously-load-development-channels server:wechat
```

### 怎么用

启动后，直接在微信里给 ClawBot 发消息即可。

示例：

- `帮我写个 Python 脚本`
- `解释一下这个项目怎么启动`
- `帮我看看这个报错是什么意思`

如果你在初始化时已经选了默认 provider，就不需要在消息里额外写前缀。

### 可选环境变量

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_AGENT_PROVIDER`

### 说明

- `Codex` 和 `OpenCode` 都是本地 CLI 方式运行
- `Claude Code` 使用官方 Channels 模式
- 微信登录凭据默认保存在用户目录下
- 同一时间只建议保留一个运行中的实例

[回到顶部](#top)

---

<a id="en"></a>

## English

Use WeChat as a front end for local coding agents. You can route messages to `Codex`, `OpenCode`, or `Claude Code` and talk to them directly from WeChat.

### What it is for

- Ask coding questions from WeChat
- Continue working with your local agent when you are away from your IDE
- Switch between multiple coding providers behind the same WeChat entry point

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

### First-time setup

Make sure the CLIs can start:

```bash
codex
opencode
claude
```

Then run:

```bash
npm run setup
```

Setup does two things:

- shows a WeChat login QR code and saves credentials
- asks you to choose the default provider

Options:

- `1` -> `Codex`
- `2` -> `OpenCode`
- `3` -> `Claude Code`

### How to start

If your default provider is `Codex` or `OpenCode`:

```bash
npm start
```

If your default provider is `Claude Code`:

```bash
claude --dangerously-load-development-channels server:wechat
```

### How to use it

After startup, just send a message to ClawBot in WeChat.

Examples:

- `Write a Python script for me`
- `Explain how this project starts`
- `What does this error mean?`

If you already selected a default provider during setup, you do not need to add any provider prefix in the message.

### Optional environment variables

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_AGENT_PROVIDER`

### Notes

- `Codex` and `OpenCode` run through their local CLIs
- `Claude Code` uses the official Channels flow
- WeChat credentials are stored in your user directory by default
- It is best to keep only one running instance at a time

[Back to top](#top)

---

License: MIT
