import fs from "fs";
import os from "os";
import path from "path";

export const DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com";
const STATE_DIR = path.join(
  process.env.WECHAT_AGENT_STATE_DIR?.trim() || path.join(os.homedir(), ".wechat-agent-channel")
);
const CREDENTIALS_DIR = path.join(STATE_DIR, "wechat");
const CREDENTIALS_FILE = path.join(CREDENTIALS_DIR, "account.json");

export function getCredentialsFile() {
  return CREDENTIALS_FILE;
}

export function loadAccount() {
  const envToken = process.env.BOT_TOKEN?.trim();
  if (envToken) {
    return {
      token: envToken,
      baseUrl: process.env.WECHAT_BASE_URL?.trim() || DEFAULT_BASE_URL,
      source: "env",
    };
  }

  try {
    if (!fs.existsSync(CREDENTIALS_FILE)) return null;
    const raw = fs.readFileSync(CREDENTIALS_FILE, "utf-8");
    const parsed = JSON.parse(raw);
    if (!parsed?.token || typeof parsed.token !== "string") return null;

    return {
      token: parsed.token.trim(),
      baseUrl: typeof parsed.baseUrl === "string" && parsed.baseUrl.trim()
        ? parsed.baseUrl.trim()
        : DEFAULT_BASE_URL,
      accountId: typeof parsed.accountId === "string" ? parsed.accountId : undefined,
      userId: typeof parsed.userId === "string" ? parsed.userId : undefined,
      savedAt: typeof parsed.savedAt === "string" ? parsed.savedAt : undefined,
      source: "file",
    };
  } catch {
    return null;
  }
}

export function saveAccount(account) {
  fs.mkdirSync(CREDENTIALS_DIR, { recursive: true });
  fs.writeFileSync(CREDENTIALS_FILE, JSON.stringify(account, null, 2), "utf-8");

  try {
    fs.chmodSync(CREDENTIALS_FILE, 0o600);
  } catch {}
}
