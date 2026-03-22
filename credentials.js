import fs from "fs";
import os from "os";
import path from "path";

export const DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com";
export const STATE_DIR = path.join(
  process.env.WECHAT_AGENT_STATE_DIR?.trim() || path.join(os.homedir(), ".wechat-agent-channel")
);
const CREDENTIALS_DIR = path.join(STATE_DIR, "wechat");
const CREDENTIALS_FILE = path.join(CREDENTIALS_DIR, "account.json");
const APP_CONFIG_FILE = path.join(STATE_DIR, "config.json");

const SUPPORTED_PROVIDERS = new Set(["claude", "codex"]);

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

export function getAppConfigFile() {
  return APP_CONFIG_FILE;
}

export function loadAppConfig() {
  const envProvider = process.env.WECHAT_AGENT_PROVIDER?.trim().toLowerCase();
  if (envProvider && SUPPORTED_PROVIDERS.has(envProvider)) {
    return { defaultProvider: envProvider, source: "env" };
  }

  try {
    if (!fs.existsSync(APP_CONFIG_FILE)) return null;
    const raw = fs.readFileSync(APP_CONFIG_FILE, "utf-8");
    const parsed = JSON.parse(raw);
    const provider = parsed?.defaultProvider?.trim?.().toLowerCase?.();
    if (!provider || !SUPPORTED_PROVIDERS.has(provider)) return null;
    return {
      defaultProvider: provider,
      savedAt: typeof parsed.savedAt === "string" ? parsed.savedAt : undefined,
      source: "file",
    };
  } catch {
    return null;
  }
}

export function saveAppConfig(config) {
  const provider = config?.defaultProvider?.trim?.().toLowerCase?.();
  if (!provider || !SUPPORTED_PROVIDERS.has(provider)) {
    throw new Error(`不支持的 provider: ${String(config?.defaultProvider)}`);
  }

  fs.mkdirSync(STATE_DIR, { recursive: true });
  fs.writeFileSync(
    APP_CONFIG_FILE,
    JSON.stringify(
      {
        defaultProvider: provider,
        savedAt: config.savedAt || new Date().toISOString(),
      },
      null,
      2
    ),
    "utf-8"
  );
}
