import qrcode from "qrcode-terminal";
import fetch from "node-fetch";

import { DEFAULT_BASE_URL, getCredentialsFile, saveAccount } from "./credentials.js";

const BOT_TYPE = "3";
const LOGIN_TIMEOUT_MS = 480_000;
const STATUS_TIMEOUT_MS = 35_000;

async function fetchQRCode(baseUrl) {
  const url = `${baseUrl}/ilink/bot/get_bot_qrcode?bot_type=${BOT_TYPE}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`获取二维码失败: HTTP ${res.status}`);
  return res.json();
}

async function pollQRStatus(baseUrl, qrcodeId) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), STATUS_TIMEOUT_MS);

  try {
    const res = await fetch(
      `${baseUrl}/ilink/bot/get_qrcode_status?qrcode=${encodeURIComponent(qrcodeId)}`,
      {
        headers: { "iLink-App-ClientVersion": "1" },
        signal: controller.signal,
      }
    );

    clearTimeout(timer);
    if (!res.ok) throw new Error(`查询扫码状态失败: HTTP ${res.status}`);
    return res.json();
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") return { status: "wait" };
    throw err;
  }
}

async function main() {
  console.log("正在获取微信登录二维码...\n");
  const qrResp = await fetchQRCode(DEFAULT_BASE_URL);

  if (qrResp?.qrcode_img_content) {
    qrcode.generate(qrResp.qrcode_img_content, { small: true });
  } else {
    console.log("二维码内容缺失，请稍后重试。");
    process.exit(1);
  }

  console.log("\n请使用微信扫描上方二维码并确认登录。\n");

  const deadline = Date.now() + LOGIN_TIMEOUT_MS;
  let scannedPrinted = false;

  while (Date.now() < deadline) {
    const status = await pollQRStatus(DEFAULT_BASE_URL, qrResp.qrcode);

    if (status.status === "wait") {
      process.stdout.write(".");
    } else if (status.status === "scaned") {
      if (!scannedPrinted) {
        console.log("\n已扫码，请在微信中确认...");
        scannedPrinted = true;
      }
    } else if (status.status === "expired") {
      console.log("\n二维码已过期，请重新运行 `npm run setup`。");
      process.exit(1);
    } else if (status.status === "confirmed") {
      if (!status.ilink_bot_id || !status.bot_token) {
        console.log("\n登录失败：服务端未返回完整凭据。");
        process.exit(1);
      }

      const account = {
        token: status.bot_token,
        baseUrl: status.baseurl || DEFAULT_BASE_URL,
        accountId: status.ilink_bot_id,
        userId: status.ilink_user_id,
        savedAt: new Date().toISOString(),
      };

      saveAccount(account);
      console.log("\n微信连接成功。");
      console.log(`账号 ID: ${account.accountId}`);
      if (account.userId) console.log(`用户 ID: ${account.userId}`);
      console.log(`凭据已保存到: ${getCredentialsFile()}`);
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  console.log("\n登录超时，请重新运行 `npm run setup`。");
  process.exit(1);
}

main().catch((err) => {
  console.error(`错误: ${String(err)}`);
  process.exit(1);
});
