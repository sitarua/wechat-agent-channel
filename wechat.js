import fetch from "node-fetch";
import { BASE_URL, BOT_TOKEN } from "./config.js";

const CHANNEL_VERSION = "0.1.0";
const LONG_POLL_TIMEOUT_MS = 35_000;

function buildHeaders(body = "") {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${BOT_TOKEN}`,
    "Content-Length": String(Buffer.byteLength(body, "utf-8")),
  };
}

/**
 * 长轮询获取微信消息
 * @param {string} getUpdatesBuf - 上次返回的游标，首次传空串
 * @returns WeChat API 原始响应（含 msgs、get_updates_buf 等）
 */
export async function getUpdates(getUpdatesBuf = "") {
  const body = JSON.stringify({
    get_updates_buf: getUpdatesBuf,
    base_info: { channel_version: CHANNEL_VERSION },
  });

  const controller = new AbortController();
  // 比服务端 timeout 多 5 秒，确保服务端先超时再我们超时
  const timer = setTimeout(() => controller.abort(), LONG_POLL_TIMEOUT_MS + 5_000);

  try {
    const res = await fetch(`${BASE_URL}/ilink/bot/getupdates`, {
      method: "POST",
      headers: buildHeaders(body),
      body,
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  } catch (err) {
    clearTimeout(timer);
    // AbortError = 正常超时，返回空结果继续轮询
    if (err.name === "AbortError") {
      return { ret: 0, msgs: [], get_updates_buf: getUpdatesBuf };
    }
    throw err;
  }
}

/**
 * 向微信用户发送文本消息
 * @param {string} context_token - 从收到的消息中取出的 context_token
 * @param {string} text - 要发送的文本内容
 */
export async function sendMessage(context_token, text) {
  const body = JSON.stringify({ context_token, content: text });

  const res = await fetch(`${BASE_URL}/ilink/bot/sendmessage`, {
    method: "POST",
    headers: buildHeaders(body),
    body,
  });

  if (!res.ok) {
    throw new Error(`sendMessage 失败: HTTP ${res.status}`);
  }
}
