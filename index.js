import fs from "fs";
import path from "path";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { getUpdates, sendMessage } from "./wechat.js";
import { routeTask } from "./router.js";
import { addTask } from "./queue.js";
import { run as runCodex } from "./sessions/codex-session.js";

const CHANNEL_NAME = "wechat";
const CHANNEL_VERSION = "0.1.0";

const MAX_CONSECUTIVE_FAILURES = 3;
const BACKOFF_DELAY_MS = 30_000;
const RETRY_DELAY_MS = 2_000;

// ── 日志（只写 stderr，stdout 留给 MCP 协议）────────────────────────────────

function log(msg) {
  process.stderr.write(`[wechat-agent] ${msg}\n`);
}

// ── context_token 缓存（sender_id → context_token，用于回复）───────────────

const contextTokenCache = new Map();

// ── MCP Server ───────────────────────────────────────────────────────────────

const mcp = new Server(
  { name: CHANNEL_NAME, version: CHANNEL_VERSION },
  {
    capabilities: {
      experimental: { "claude/channel": {} },
      tools: {},
    },
    instructions: [
      "你是通过微信与用户交流的 AI 助手。",
      "用户消息以 <channel source=\"wechat\" sender=\"...\" sender_id=\"...\"> 格式到达。",
      "使用 wechat_reply 工具回复。必须传入消息中的 sender_id。",
      "用中文回复（除非用户用其他语言）。",
      "保持回复简洁——微信不渲染 Markdown，请用纯文本。",
    ].join("\n"),
  }
);

// 注册 wechat_reply 工具：Claude Code 用它把回复发回微信
mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "wechat_reply",
      description: "向微信用户发送文本回复",
      inputSchema: {
        type: "object",
        properties: {
          sender_id: {
            type: "string",
            description: "来自 <channel> 标签的 sender_id（xxx@im.wechat 格式）",
          },
          text: {
            type: "string",
            description: "要发送的纯文本消息，不要使用 Markdown",
          },
        },
        required: ["sender_id", "text"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name === "wechat_reply") {
    const { sender_id, text } = req.params.arguments;
    const contextToken = contextTokenCache.get(sender_id);
    if (!contextToken) {
      return {
        content: [
          {
            type: "text",
            text: `error: 找不到 ${sender_id} 的 context_token，该用户可能还没发过消息`,
          },
        ],
      };
    }
    try {
      await sendMessage(contextToken, text.slice(0, 1000));
      return { content: [{ type: "text", text: "sent" }] };
    } catch (err) {
      return {
        content: [{ type: "text", text: `send failed: ${String(err)}` }],
      };
    }
  }
  throw new Error(`unknown tool: ${req.params.name}`);
});

// ── WeChat 长轮询主循环 ───────────────────────────────────────────────────────

async function startPolling() {
  let getUpdatesBuf = "";
  let consecutiveFailures = 0;

  // 持久化同步游标（重启后继续，不重复收消息）
  const syncBufFile = path.join(
    process.env.USERPROFILE || process.env.HOME || ".",
    ".wechat-agent-sync-buf"
  );
  try {
    if (fs.existsSync(syncBufFile)) {
      getUpdatesBuf = fs.readFileSync(syncBufFile, "utf-8");
      log(`恢复上次同步状态`);
    }
  } catch {}

  log("开始监听微信消息...");

  while (true) {
    try {
      const resp = await getUpdates(getUpdatesBuf);

      const isError =
        (resp.ret !== undefined && resp.ret !== 0) ||
        (resp.errcode !== undefined && resp.errcode !== 0);

      if (isError) {
        consecutiveFailures++;
        log(`getUpdates 失败: ret=${resp.ret} errcode=${resp.errcode} errmsg=${resp.errmsg ?? ""}`);
        if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
          log(`连续失败 ${MAX_CONSECUTIVE_FAILURES} 次，等待 ${BACKOFF_DELAY_MS / 1000}s...`);
          consecutiveFailures = 0;
          await sleep(BACKOFF_DELAY_MS);
        } else {
          await sleep(RETRY_DELAY_MS);
        }
        continue;
      }

      consecutiveFailures = 0;

      // 持久化游标
      if (resp.get_updates_buf) {
        getUpdatesBuf = resp.get_updates_buf;
        try { fs.writeFileSync(syncBufFile, getUpdatesBuf, "utf-8"); } catch {}
      }

      for (const msg of resp.msgs ?? []) {
        // 只处理用户发来的消息（message_type === 1），跳过机器人自己的消息
        if (msg.message_type !== 1) continue;

        const text = extractText(msg);
        if (!text) continue;

        const senderId = msg.from_user_id ?? "unknown";
        if (msg.context_token) {
          contextTokenCache.set(senderId, msg.context_token);
        }

        log(`收到消息: from=${senderId.split("@")[0]} text=${text.slice(0, 60)}`);

        const route = routeTask(text);

        if (route === "codex") {
          // ── Codex 路由：我们自己处理，维护会话历史 ──────────────────────
          addTask(async () => {
            log(`[codex] 处理来自 ${senderId.split("@")[0]} 的消息...`);
            const result = await runCodex(senderId, text);
            const ctx = contextTokenCache.get(senderId);
            if (ctx) {
              await sendMessage(ctx, result.slice(0, 1000));
            }
          });
        } else {
          // ── Claude 路由：推送给 Claude Code session，让 Claude 回复 ──────
          addTask(async () => {
            log(`[claude] 推送消息到 Claude Code session...`);
            await mcp.notification({
              method: "notifications/claude/channel",
              params: {
                content: text,
                meta: {
                  sender: senderId.split("@")[0] || senderId,
                  sender_id: senderId,
                },
              },
            });
          });
        }
      }
    } catch (err) {
      consecutiveFailures++;
      log(`轮询异常: ${String(err)}`);
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        consecutiveFailures = 0;
        await sleep(BACKOFF_DELAY_MS);
      } else {
        await sleep(RETRY_DELAY_MS);
      }
    }
  }
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function extractText(msg) {
  if (!msg.item_list?.length) return "";
  for (const item of msg.item_list) {
    if (item.type === 1 && item.text_item?.text) {
      const text = item.text_item.text;
      const ref = item.ref_msg;
      if (!ref) return text;
      const parts = [];
      if (ref.title) parts.push(ref.title);
      return parts.length ? `[引用: ${parts.join(" | ")}]\n${text}` : text;
    }
    if (item.type === 3 && item.voice_item?.text) {
      return item.voice_item.text;
    }
  }
  return "";
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── 入口 ─────────────────────────────────────────────────────────────────────

async function main() {
  if (!process.env.BOT_TOKEN) {
    log("⚠️  警告：BOT_TOKEN 环境变量未设置，微信 API 请求将会失败");
  }

  // 先建立 MCP 连接（Claude Code 等待 stdio 握手）
  await mcp.connect(new StdioServerTransport());
  log("MCP 连接就绪");

  // 启动长轮询（永不退出）
  await startPolling();
}

main().catch((err) => {
  process.stderr.write(`[wechat-agent] Fatal: ${String(err)}\n`);
  process.exit(1);
});
