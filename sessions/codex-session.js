import fs from "fs";
import path from "path";
import net from "net";
import { spawn, spawnSync } from "child_process";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const STORE_FILE = path.join(__dirname, "codex-threads.json");
const APP_SERVER_HOST = "127.0.0.1";
const DEFAULT_MODEL = process.env.CODEX_MODEL || "gpt-5-codex";
const DEFAULT_TIMEOUT_MS = 120_000;
const TIMEOUT_MS = getTimeoutMs();

let child = null;
let ws = null;
let connectionPromise = null;
let requestId = 1;
const pending = new Map();
const notificationListeners = new Set();

const threadStore = loadThreadStore();

function log(msg) {
  process.stderr.write(`[codex-session] ${msg}\n`);
}

function getTimeoutMs() {
  const raw = process.env.CODEX_TURN_TIMEOUT_MS?.trim();
  if (!raw) return DEFAULT_TIMEOUT_MS;

  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    return DEFAULT_TIMEOUT_MS;
  }

  return Math.floor(value);
}

function resolveCodexLaunchSpec() {
  const override = process.env.CODEX_BIN?.trim();
  if (override) {
    return { command: override, args: [] };
  }

  if (process.platform !== "win32") {
    return { command: "codex", args: [] };
  }

  try {
    const result = spawnSync("where.exe", ["codex.exe"], { encoding: "utf-8" });
    if (result.status === 0) {
      const command = result.stdout
        .split(/\r?\n/)
        .map((line) => line.trim())
        .find(Boolean);

      if (command) {
        return { command, args: [] };
      }
    }
  } catch {}

  return { command: "cmd.exe", args: ["/d", "/s", "/c", "codex.cmd"] };
}

function loadThreadStore() {
  try {
    if (!fs.existsSync(STORE_FILE)) return {};
    return JSON.parse(fs.readFileSync(STORE_FILE, "utf-8"));
  } catch (err) {
    log(`读取 thread store 失败，改用空状态: ${String(err)}`);
    return {};
  }
}

function saveThreadStore() {
  try {
    fs.writeFileSync(STORE_FILE, JSON.stringify(threadStore, null, 2), "utf-8");
  } catch (err) {
    log(`写入 thread store 失败: ${String(err)}`);
  }
}

function clearThreadStore() {
  for (const key of Object.keys(threadStore)) {
    delete threadStore[key];
  }
  saveThreadStore();
}

function resetConnectionState(error) {
  const socket = ws;
  ws = null;

  if (socket && socket.readyState === WebSocket.OPEN) {
    try {
      socket.close();
    } catch {}
  }
  connectionPromise = null;
  notificationListeners.clear();

  for (const [, entry] of pending) {
    entry.reject(error);
  }
  pending.clear();
}

function cleanupChild() {
  if (!child) return;
  try {
    child.kill("SIGTERM");
  } catch {}
  child = null;
}

function isTimeoutError(err) {
  const message = err?.message || String(err);
  return message.includes("超时");
}

async function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, APP_SERVER_HOST, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close((err) => {
        if (err) return reject(err);
        if (!port) return reject(new Error("无法获取空闲端口"));
        resolve(port);
      });
    });
    server.on("error", reject);
  });
}

async function ensureServer() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }
  if (connectionPromise) {
    return connectionPromise;
  }

  connectionPromise = (async () => {
    const port = await getFreePort();
    const url = `ws://${APP_SERVER_HOST}:${port}`;
    const launch = resolveCodexLaunchSpec();

    // app-server 重启后，旧 thread id 会失效；启动新 server 时清空本地映射
    clearThreadStore();

    child = spawn(launch.command, [...launch.args, "app-server", "--listen", url], {
      env: { ...process.env, NO_COLOR: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });

    child.once("error", (err) => {
      log(`启动 Codex 失败 (${launch.command}): ${String(err)}`);
      resetConnectionState(err);
      child = null;
    });

    child.stdout.on("data", (data) => {
      const text = data.toString().trim();
      if (text) log(`[app-server] ${text}`);
    });

    child.stderr.on("data", (data) => {
      const text = data.toString().trim();
      if (text) log(`[app-server] ${text}`);
    });

    child.once("exit", (code, signal) => {
      const err = new Error(`codex app-server 已退出 (code=${code}, signal=${signal})`);
      resetConnectionState(err);
      child = null;
    });

    await connectWebSocket(url);
    await sendRequest("initialize", {
      clientInfo: {
        name: "wechat-agent-channel",
        title: "WeChat Agent Channel",
        version: "0.1.0",
      },
      capabilities: {
        experimentalApi: true,
      },
    });
  })();

  try {
    await connectionPromise;
  } catch (err) {
    cleanupChild();
    resetConnectionState(err);
    throw err;
  } finally {
    connectionPromise = null;
  }
}

async function connectWebSocket(url) {
  let lastError = null;

  for (let attempt = 0; attempt < 40; attempt++) {
    try {
      await new Promise((resolve, reject) => {
        const socket = new WebSocket(url);

        socket.onopen = () => {
          ws = socket;
          attachSocketHandlers(socket);
          resolve();
        };

        socket.onerror = () => {
          reject(new Error(`连接 ${url} 失败`));
        };
      });
      return;
    } catch (err) {
      lastError = err;
      await sleep(250);
    }
  }

  throw lastError || new Error(`连接 ${url} 超时`);
}

function attachSocketHandlers(socket) {
  socket.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data.toString());
    } catch (err) {
      log(`收到无法解析的消息: ${String(err)}`);
      return;
    }

    if (msg.id !== undefined) {
      const entry = pending.get(msg.id);
      if (!entry) return;
      pending.delete(msg.id);

      if (msg.error) {
        entry.reject(new Error(msg.error.message || JSON.stringify(msg.error)));
      } else {
        entry.resolve(msg.result);
      }
      return;
    }

    for (const listener of notificationListeners) {
      try {
        listener(msg);
      } catch (err) {
        log(`通知监听器异常: ${String(err)}`);
      }
    }
  };

  socket.onclose = () => {
    if (ws === socket) {
      resetConnectionState(new Error("Codex app-server 连接已关闭"));
    }
  };
}

function sendRequest(method, params, { timeoutMs = TIMEOUT_MS } = {}) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return Promise.reject(new Error("Codex app-server 未连接"));
  }

  const id = requestId++;

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`${method} 超时`));
    }, timeoutMs);

    pending.set(id, {
      resolve: (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      reject: (err) => {
        clearTimeout(timer);
        reject(err);
      },
    });

    ws.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
  });
}

async function ensureThread(userId) {
  const existingThreadId = threadStore[userId];
  if (existingThreadId) {
    return existingThreadId;
  }

  const result = await sendRequest("thread/start", {
    cwd: process.cwd(),
    model: DEFAULT_MODEL,
    approvalPolicy: "never",
    experimentalRawEvents: false,
    persistExtendedHistory: true,
    developerInstructions: [
      "你通过微信与用户交流。",
      "默认用中文回复，除非用户明确使用其他语言。",
      "回复尽量直接、简洁、可执行。",
      "微信不渲染 Markdown，尽量输出纯文本。",
    ].join("\n"),
  });

  const threadId = result?.thread?.id;
  if (!threadId) {
    throw new Error("thread/start 未返回 threadId");
  }

  threadStore[userId] = threadId;
  saveThreadStore();
  return threadId;
}

function buildTurnResult(state) {
  const text = state.messageOrder
    .map((itemId) => state.messages.get(itemId) || "")
    .join("")
    .trim();

  if (text) return text;
  if (state.error) return `❌ Codex 执行失败：${state.error}`;
  return "Codex 已完成，但没有返回可发送的文本。";
}

async function startTurn(threadId, userMessage) {
  const state = {
    messages: new Map(),
    messageOrder: [],
    error: "",
  };

  let currentTurnId = null;

  return new Promise(async (resolve, reject) => {
    const timer = setTimeout(() => {
      log(`等待 turn/completed 超时 (${TIMEOUT_MS}ms, thread=${threadId})`);
      notificationListeners.delete(onNotification);
      reject(new Error("等待 turn/completed 超时"));
    }, TIMEOUT_MS);

    const finish = (fn, value) => {
      clearTimeout(timer);
      notificationListeners.delete(onNotification);
      fn(value);
    };

    const onNotification = (msg) => {
      const params = msg.params || {};
      if (params.threadId !== threadId) return;
      if (currentTurnId && params.turnId && params.turnId !== currentTurnId) return;

      if (msg.method === "item/agentMessage/delta") {
        const itemId = params.itemId;
        if (!state.messages.has(itemId)) {
          state.messages.set(itemId, "");
          state.messageOrder.push(itemId);
        }
        state.messages.set(itemId, state.messages.get(itemId) + (params.delta || ""));
        return;
      }

      if (msg.method === "item/completed" && params.item?.type === "agentMessage") {
        const itemId = params.item.id;
        if (!state.messages.has(itemId)) {
          state.messageOrder.push(itemId);
        }
        state.messages.set(itemId, params.item.text || state.messages.get(itemId) || "");
        return;
      }

      if (msg.method === "error") {
        state.error = params.error?.message || "未知错误";
        return;
      }

      if (msg.method === "turn/completed") {
        finish(resolve, buildTurnResult(state));
      }
    };

    notificationListeners.add(onNotification);

    try {
      const result = await sendRequest("turn/start", {
        threadId,
        input: [
          {
            type: "text",
            text: userMessage,
            text_elements: [],
          },
        ],
      });
      currentTurnId = result?.turn?.id || null;
      log(
        `已提交到 Codex，等待 turn/completed (thread=${threadId}, turn=${currentTurnId || "unknown"}, timeout=${TIMEOUT_MS}ms)`
      );
    } catch (err) {
      finish(reject, err);
    }
  });
}

async function runOnce(userId, userMessage) {
  await ensureServer();
  const threadId = await ensureThread(userId);
  return startTurn(threadId, userMessage);
}

export async function run(userId, userMessage) {
  try {
    return await runOnce(userId, userMessage);
  } catch (err) {
    log(`首次执行失败，尝试重建线程: ${String(err)}`);
    if (isTimeoutError(err)) {
      cleanupChild();
      resetConnectionState(err);
      return "❌ Codex 10 秒内没有返回结果，请稍后重试。";
    }

    delete threadStore[userId];
    saveThreadStore();

    try {
      return await runOnce(userId, userMessage);
    } catch (retryErr) {
      if (isTimeoutError(retryErr)) {
        cleanupChild();
        resetConnectionState(retryErr);
        return "❌ Codex 10 秒内没有返回结果，请稍后重试。";
      }
      return `❌ Codex 执行失败：${retryErr.message || String(retryErr)}`;
    }
  }
}

export function clearSession(userId) {
  delete threadStore[userId];
  saveThreadStore();
}

export function getSessionStats() {
  const stats = {};
  for (const [userId, threadId] of Object.entries(threadStore)) {
    stats[userId.split("@")[0]] = threadId;
  }
  return stats;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

for (const signal of ["SIGINT", "SIGTERM", "exit"]) {
  process.on(signal, () => {
    cleanupChild();
  });
}
