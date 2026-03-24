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

也可以直接发附件：

- 图片
- 文件
- 语音
- 视频

附件会先保存到当前项目下的 `.wechat-agent/attachments/`，再交给 agent 读取。

如果你已经选了默认 provider，就不用再写前缀。

### 会话命令

- `/new` 或 `新任务`
- `/new 重构支付`
- `/list` 或 `会话列表`
- `/current` 或 `当前会话`
- `/switch 2` 或 `切换会话 2`
- `/delete 2` 或 `删除会话 2`
- `/clear` 或 `清空会话`

### OpenCode 模型命令

- `/models` 或 `模型列表`
- `/model`
- `/model m2.5`
- `/model clear`

### 常用环境变量

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_CDN_BASE_URL`
- `WECHAT_AGENT_PROVIDER`
- `CODEX_MODEL`
- `CODEX_TURN_TIMEOUT_MS`
- `CODEX_BIN`
- `OPENCODE_MODEL`
- `OPENCODE_TURN_TIMEOUT_MS`
- `OPENCODE_THINKING`
- `OPENCODE_BIN`

### 说明

- `Codex` 和 `OpenCode` 走本地 CLI
- `Claude Code` 走独立 MCP 插件模式
- 当前项目调用 `Codex` 时默认使用 `--dangerously-bypass-approvals-and-sandbox`，这样本地 CLI 才能真正拿到完整执行权限；请只在你信任的本机环境里使用
- 当前项目支持把微信图片、文件、语音、视频保存到本地并交给 agent 使用
- `Codex` / `OpenCode` 如需回传本地文件，可在最终回复末尾输出 `wechat-reply` JSON 代码块，桥会按其中的 `media_paths` 回传到微信
- 微信登录凭据默认保存在用户目录下

### 致谢

部分附件处理和接入思路参考了 `cc-connect`：

- https://github.com/chenhg5/cc-connect

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

You can also send attachments:

- Images
- Files
- Voice messages
- Videos

Attachments are first saved to `.wechat-agent/attachments/` in the current project, then handed off to the agent.

If you already chose a default provider, you do not need to add a prefix.

### Session Commands

- `/new` or `新任务`
- `/new payment-refactor`
- `/list` or `会话列表`
- `/current` or `当前会话`
- `/switch 2` or `切换会话 2`
- `/delete 2` or `删除会话 2`
- `/clear` or `清空会话`

### OpenCode Model Commands

- `/models` or `模型列表`
- `/model`
- `/model m2.5`
- `/model clear`

### Common environment variables

- `BOT_TOKEN`
- `WECHAT_BASE_URL`
- `WECHAT_CDN_BASE_URL`
- `WECHAT_AGENT_PROVIDER`
- `CODEX_MODEL`
- `CODEX_TURN_TIMEOUT_MS`
- `CODEX_BIN`
- `OPENCODE_MODEL`
- `OPENCODE_TURN_TIMEOUT_MS`
- `OPENCODE_THINKING`
- `OPENCODE_BIN`

### Notes

- `Codex` and `OpenCode` run through local CLIs
- `Claude Code` uses a separate MCP plugin flow
- This project invokes `Codex` with `--dangerously-bypass-approvals-and-sandbox` so the local CLI actually gets full execution permissions; only use it on a machine you trust
- The project can save inbound WeChat images, files, voice, and video locally before handing them to the agent
- `Codex` / `OpenCode` can return local files to WeChat by appending a `wechat-reply` JSON code block with `media_paths` at the end of the final reply
- WeChat credentials are stored in your user directory by default

### Acknowledgement

Some of the attachment and integration ideas were inspired by:

- https://github.com/chenhg5/cc-connect

[Back to top](#top)

---

License: MIT
