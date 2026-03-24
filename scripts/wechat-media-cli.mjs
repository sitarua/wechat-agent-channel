#!/usr/bin/env node

import crypto from "node:crypto";
import fsSync from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");

function loadChannelVersion() {
  try {
    const raw = fsSync.readFileSync(path.join(REPO_ROOT, "version.json"), "utf-8");
    const parsed = JSON.parse(raw);
    const version = String(parsed?.version || "").trim();
    return version || "1.2.1";
  } catch {
    return "1.2.1";
  }
}

const CHANNEL_VERSION = `wechat-agent-channel/${loadChannelVersion()}`;

const MESSAGE_ITEM_TYPE = {
  TEXT: 1,
  IMAGE: 2,
  VOICE: 3,
  FILE: 4,
  VIDEO: 5,
};

const UPLOAD_MEDIA_TYPE = {
  IMAGE: 1,
  VIDEO: 2,
  FILE: 3,
};

const EXT_TO_MIME = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".bmp": "image/bmp",
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".avi": "video/x-msvideo",
  ".pdf": "application/pdf",
  ".txt": "text/plain",
  ".md": "text/markdown",
  ".json": "application/json",
  ".csv": "text/csv",
  ".zip": "application/zip",
  ".doc": "application/msword",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xls": "application/vnd.ms-excel",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".ppt": "application/vnd.ms-powerpoint",
  ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".amr": "audio/amr",
  ".mp3": "audio/mpeg",
  ".ogg": "audio/ogg",
  ".wav": "audio/wav",
  ".silk": "audio/silk",
};

function randomWechatUin() {
  const value = crypto.randomBytes(4).readUInt32BE(0);
  return Buffer.from(String(value), "utf-8").toString("base64");
}

function ensureTrailingSlash(url) {
  return url.endsWith("/") ? url : `${url}/`;
}

function buildHeaders(token, body, extra = {}) {
  const headers = {
    "Content-Type": "application/json",
    AuthorizationType: "ilink_bot_token",
    Authorization: `Bearer ${token}`,
    "X-WECHAT-UIN": randomWechatUin(),
    ...extra,
  };
  if (body != null) {
    headers["Content-Length"] = String(Buffer.byteLength(body));
  }
  return headers;
}

async function postJson(account, endpoint, payload) {
  const body = JSON.stringify({ ...payload, base_info: { channel_version: CHANNEL_VERSION } });
  const url = new URL(endpoint, ensureTrailingSlash(account.baseUrl));
  const res = await fetch(url, {
    method: "POST",
    headers: buildHeaders(account.token, body),
    body,
  });
  const raw = await res.text();
  if (!res.ok) {
    throw new Error(`${endpoint} ${res.status}: ${raw}`);
  }
  const parsed = raw ? JSON.parse(raw) : {};
  if (parsed && typeof parsed === "object") {
    const ret = parsed.ret;
    const errcode = parsed.errcode;
    if (!([undefined, null, 0].includes(ret) && [undefined, null, 0].includes(errcode))) {
      throw new Error(`${endpoint} failed: ${JSON.stringify({ ret, errcode, errmsg: parsed.errmsg || parsed.msg || "" })}`);
    }
  }
  return parsed;
}

function buildCdnDownloadUrl(cdnBaseUrl, encryptedQueryParam) {
  return `${cdnBaseUrl}/download?encrypted_query_param=${encodeURIComponent(encryptedQueryParam)}`;
}

function buildCdnUploadUrl(cdnBaseUrl, uploadParam, filekey) {
  return `${cdnBaseUrl}/upload?encrypted_query_param=${encodeURIComponent(uploadParam)}&filekey=${encodeURIComponent(filekey)}`;
}

function parseAesKey(aesKeyBase64) {
  const decoded = Buffer.from(aesKeyBase64, "base64");
  if (decoded.length === 16) {
    return decoded;
  }
  if (decoded.length === 32 && /^[0-9a-fA-F]{32}$/.test(decoded.toString("ascii"))) {
    return Buffer.from(decoded.toString("ascii"), "hex");
  }
  throw new Error(`invalid aes_key length: ${decoded.length}`);
}

function decryptAesEcb(ciphertext, key) {
  const decipher = crypto.createDecipheriv("aes-128-ecb", key, null);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}

function encryptAesEcb(plaintext, key) {
  const cipher = crypto.createCipheriv("aes-128-ecb", key, null);
  return Buffer.concat([cipher.update(plaintext), cipher.final()]);
}

function aesEcbPaddedSize(plaintextSize) {
  return Math.ceil((plaintextSize + 1) / 16) * 16;
}

async function fetchBuffer(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`fetch failed ${res.status} ${res.statusText}: ${url}`);
  }
  return Buffer.from(await res.arrayBuffer());
}

async function downloadAndDecryptMedia(encryptedQueryParam, aesKeyBase64, cdnBaseUrl) {
  const encrypted = await fetchBuffer(buildCdnDownloadUrl(cdnBaseUrl, encryptedQueryParam));
  if (!aesKeyBase64) {
    return encrypted;
  }
  return decryptAesEcb(encrypted, parseAesKey(aesKeyBase64));
}

function detectImageExtension(buf) {
  if (buf.length >= 8 && buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
    return ".png";
  }
  if (buf.length >= 3 && buf.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff]))) {
    return ".jpg";
  }
  if (buf.length >= 6) {
    const head = buf.subarray(0, 6).toString("ascii");
    if (head === "GIF87a" || head === "GIF89a") {
      return ".gif";
    }
  }
  if (buf.length >= 12 && buf.subarray(0, 4).toString("ascii") === "RIFF" && buf.subarray(8, 12).toString("ascii") === "WEBP") {
    return ".webp";
  }
  if (buf.length >= 2 && buf.subarray(0, 2).equals(Buffer.from([0x42, 0x4d]))) {
    return ".bmp";
  }
  return ".png";
}

function mimeFromExtension(ext) {
  return EXT_TO_MIME[ext.toLowerCase()] || "application/octet-stream";
}

function mimeFromFilePath(filePath) {
  return mimeFromExtension(path.extname(filePath));
}

function ensureFileName(name, fallback) {
  const trimmed = String(name || "").trim();
  return trimmed || fallback;
}

function uniqueName(prefix, ext) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}${ext}`;
}

async function saveBuffer(baseDir, fileName, buf) {
  await fs.mkdir(baseDir, { recursive: true });
  const resolved = path.join(baseDir, fileName);
  await fs.writeFile(resolved, buf);
  return resolved;
}

function collectCandidateMediaItems(itemList) {
  const result = [];
  const seen = new Set();

  for (const item of itemList || []) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const direct = item.type;
    if ([MESSAGE_ITEM_TYPE.IMAGE, MESSAGE_ITEM_TYPE.VOICE, MESSAGE_ITEM_TYPE.FILE, MESSAGE_ITEM_TYPE.VIDEO].includes(direct)) {
      const key = `${direct}:${JSON.stringify(item.media || item.image_item?.media || item.voice_item?.media || item.file_item?.media || item.video_item?.media || {})}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(item);
      }
    }
    const refItem = item.ref_msg?.message_item;
    if (refItem && [MESSAGE_ITEM_TYPE.IMAGE, MESSAGE_ITEM_TYPE.VOICE, MESSAGE_ITEM_TYPE.FILE, MESSAGE_ITEM_TYPE.VIDEO].includes(refItem.type)) {
      const key = `ref:${refItem.type}:${JSON.stringify(refItem.media || refItem.image_item?.media || refItem.voice_item?.media || refItem.file_item?.media || refItem.video_item?.media || {})}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(refItem);
      }
    }
  }

  return result;
}

async function collectInboundMedia(input) {
  const { account, message, workDir } = input;
  const attachDir = path.join(workDir, ".wechat-agent", "attachments");
  const images = [];
  const files = [];

  for (const item of collectCandidateMediaItems(message?.item_list)) {
    if (item.type === MESSAGE_ITEM_TYPE.IMAGE) {
      const media = item.image_item?.media;
      if (!media?.encrypt_query_param) {
        continue;
      }
      const aesKeyBase64 = item.image_item?.aeskey
        ? Buffer.from(item.image_item.aeskey, "hex").toString("base64")
        : media.aes_key;
      const buf = await downloadAndDecryptMedia(media.encrypt_query_param, aesKeyBase64, account.cdnBaseUrl);
      const ext = detectImageExtension(buf);
      const fileName = uniqueName("image", ext);
      const savedPath = await saveBuffer(attachDir, fileName, buf);
      images.push({
        kind: "image",
        path: savedPath,
        fileName,
        mimeType: mimeFromExtension(ext),
      });
      continue;
    }

    if (item.type === MESSAGE_ITEM_TYPE.FILE) {
      const media = item.file_item?.media;
      if (!media?.encrypt_query_param || !media.aes_key) {
        continue;
      }
      const buf = await downloadAndDecryptMedia(media.encrypt_query_param, media.aes_key, account.cdnBaseUrl);
      const fileName = ensureFileName(item.file_item?.file_name, uniqueName("file", ".bin"));
      const savedPath = await saveBuffer(attachDir, fileName, buf);
      files.push({
        kind: "file",
        path: savedPath,
        fileName,
        mimeType: mimeFromFilePath(fileName),
      });
      continue;
    }

    if (item.type === MESSAGE_ITEM_TYPE.VIDEO) {
      const media = item.video_item?.media;
      if (!media?.encrypt_query_param || !media.aes_key) {
        continue;
      }
      const buf = await downloadAndDecryptMedia(media.encrypt_query_param, media.aes_key, account.cdnBaseUrl);
      const fileName = uniqueName("video", ".mp4");
      const savedPath = await saveBuffer(attachDir, fileName, buf);
      files.push({
        kind: "video",
        path: savedPath,
        fileName,
        mimeType: "video/mp4",
      });
      continue;
    }

    if (item.type === MESSAGE_ITEM_TYPE.VOICE) {
      const media = item.voice_item?.media;
      if (!media?.encrypt_query_param || !media.aes_key) {
        continue;
      }
      const encodeType = Number(item.voice_item?.encode_type || 0);
      const ext = encodeType === 7 ? ".mp3" : encodeType === 8 ? ".ogg" : encodeType === 5 ? ".amr" : ".silk";
      const buf = await downloadAndDecryptMedia(media.encrypt_query_param, media.aes_key, account.cdnBaseUrl);
      const fileName = uniqueName("voice", ext);
      const savedPath = await saveBuffer(attachDir, fileName, buf);
      files.push({
        kind: "audio",
        path: savedPath,
        fileName,
        mimeType: mimeFromExtension(ext),
      });
    }
  }

  return { images, files };
}

async function getUploadUrl(account, payload) {
  return postJson(account, "ilink/bot/getuploadurl", payload);
}

async function sendMessage(account, payload) {
  return postJson(account, "ilink/bot/sendmessage", payload);
}

async function uploadBufferToCdn(account, buf, uploadParam, filekey, aeskey) {
  const ciphertext = encryptAesEcb(buf, aeskey);
  const url = buildCdnUploadUrl(account.cdnBaseUrl, uploadParam, filekey);

  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
        },
        body: ciphertext,
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`cdn upload failed ${res.status}: ${body}`);
      }
      const encryptedParam = res.headers.get("x-encrypted-param");
      if (!encryptedParam) {
        throw new Error("cdn upload missing x-encrypted-param");
      }
      return encryptedParam;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function uploadMedia(account, toUserId, filePath, mediaType) {
  const plaintext = await fs.readFile(filePath);
  const rawsize = plaintext.length;
  const rawfilemd5 = crypto.createHash("md5").update(plaintext).digest("hex");
  const filesize = aesEcbPaddedSize(rawsize);
  const filekey = crypto.randomBytes(16).toString("hex");
  const aeskey = crypto.randomBytes(16);

  const uploadMeta = await getUploadUrl(account, {
    filekey,
    media_type: mediaType,
    to_user_id: toUserId,
    rawsize,
    rawfilemd5,
    filesize,
    no_need_thumb: true,
    aeskey: aeskey.toString("hex"),
  });

  if (!uploadMeta?.upload_param) {
    throw new Error("getuploadurl returned no upload_param");
  }

  const encryptedQueryParam = await uploadBufferToCdn(account, plaintext, uploadMeta.upload_param, filekey, aeskey);
  return {
    fileSize: rawsize,
    fileSizeCiphertext: filesize,
    encryptedQueryParam,
    aesKeyBase64: Buffer.from(aeskey.toString("hex"), "utf-8").toString("base64"),
  };
}

function buildTextPayload(toUserId, contextToken, text) {
  return {
    msg: {
      from_user_id: "",
      to_user_id: toUserId,
      client_id: `wechat-agent:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
      message_type: 2,
      message_state: 2,
      item_list: [
        {
          type: MESSAGE_ITEM_TYPE.TEXT,
          text_item: { text },
        },
      ],
      context_token: contextToken,
    },
  };
}

function buildMediaPayload(toUserId, contextToken, mediaPath, uploaded) {
  const mime = mimeFromFilePath(mediaPath);
  const base = {
    msg: {
      from_user_id: "",
      to_user_id: toUserId,
      client_id: `wechat-agent:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
      message_type: 2,
      message_state: 2,
      context_token: contextToken,
    },
  };

  if (mime.startsWith("image/")) {
    base.msg.item_list = [
      {
        type: MESSAGE_ITEM_TYPE.IMAGE,
        image_item: {
          media: {
            encrypt_query_param: uploaded.encryptedQueryParam,
            aes_key: uploaded.aesKeyBase64,
            encrypt_type: 1,
          },
          mid_size: uploaded.fileSizeCiphertext,
        },
      },
    ];
    return base;
  }

  if (mime.startsWith("video/")) {
    base.msg.item_list = [
      {
        type: MESSAGE_ITEM_TYPE.VIDEO,
        video_item: {
          media: {
            encrypt_query_param: uploaded.encryptedQueryParam,
            aes_key: uploaded.aesKeyBase64,
            encrypt_type: 1,
          },
          video_size: uploaded.fileSizeCiphertext,
        },
      },
    ];
    return base;
  }

  base.msg.item_list = [
    {
      type: MESSAGE_ITEM_TYPE.FILE,
      file_item: {
        media: {
          encrypt_query_param: uploaded.encryptedQueryParam,
          aes_key: uploaded.aesKeyBase64,
          encrypt_type: 1,
        },
        file_name: path.basename(mediaPath),
        len: String(uploaded.fileSize),
      },
    },
  ];
  return base;
}

async function sendOutboundMedia(input) {
  const { account, toUserId, contextToken, text, mediaPath, workDir } = input;
  if (!mediaPath) {
    throw new Error("mediaPath is required");
  }
  const resolvedPath = path.isAbsolute(mediaPath) ? mediaPath : path.resolve(workDir, mediaPath);
  const mime = mimeFromFilePath(resolvedPath);
  const mediaType = mime.startsWith("image/")
    ? UPLOAD_MEDIA_TYPE.IMAGE
    : mime.startsWith("video/")
      ? UPLOAD_MEDIA_TYPE.VIDEO
      : UPLOAD_MEDIA_TYPE.FILE;

  if (text && String(text).trim()) {
    await sendMessage(account, buildTextPayload(toUserId, contextToken, String(text).slice(0, 1000)));
  }

  const uploaded = await uploadMedia(account, toUserId, resolvedPath, mediaType);
  await sendMessage(account, buildMediaPayload(toUserId, contextToken, resolvedPath, uploaded));
  return { ok: true };
}

async function readStdinJson() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf-8").trim();
  return raw ? JSON.parse(raw) : {};
}

async function main() {
  const command = process.argv[2];
  const input = await readStdinJson();

  if (!input?.account?.token || !input?.account?.baseUrl || !input?.account?.cdnBaseUrl) {
    throw new Error("account.token/baseUrl/cdnBaseUrl are required");
  }

  if (command === "collect-inbound") {
    const result = await collectInboundMedia(input);
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return;
  }

  if (command === "send-media") {
    const result = await sendOutboundMedia(input);
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return;
  }

  throw new Error(`unknown command: ${command}`);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || String(error)}\n`);
  process.exit(1);
});
