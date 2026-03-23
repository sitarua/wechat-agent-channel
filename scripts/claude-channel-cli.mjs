#!/usr/bin/env node

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");
const runPython = resolve(repoRoot, "scripts", "run-python.js");

function runPythonScript(script, args = []) {
  const result = spawnSync("node", [runPython, script, ...args], {
    cwd: repoRoot,
    stdio: "inherit",
    env: process.env,
  });
  process.exit(result.status ?? 1);
}

function install() {
  const mcpConfig = {
    mcpServers: {
      wechat: {
        command: "node",
        args: ["scripts/run-python.js", "claude_channel.py"],
      },
    },
  };

  const mcpPath = resolve(process.cwd(), ".mcp.json");

  if (existsSync(mcpPath)) {
    try {
      const existing = JSON.parse(readFileSync(mcpPath, "utf-8"));
      existing.mcpServers = existing.mcpServers || {};
      existing.mcpServers.wechat = mcpConfig.mcpServers.wechat;
      writeFileSync(mcpPath, JSON.stringify(existing, null, 2) + "\n", "utf-8");
      console.log(`Updated: ${mcpPath}`);
      return;
    } catch {
      // Fall through and rewrite the file.
    }
  }

  writeFileSync(mcpPath, JSON.stringify(mcpConfig, null, 2) + "\n", "utf-8");
  console.log(`Created: ${mcpPath}`);
}

function help() {
  console.log(`
Claude WeChat Channel

Usage: node scripts/claude-channel-cli.mjs <command>

Commands:
  setup     WeChat QR login for Claude channel mode
  start     Start the Claude channel MCP server
  install   Write/update .mcp.json in the current directory
  help      Show this help message
`);
}

const command = process.argv[2];

switch (command) {
  case "setup":
    runPythonScript("claude_setup.py");
    break;
  case "start":
    runPythonScript("claude_channel.py");
    break;
  case "install":
    install();
    break;
  case "help":
  case "--help":
  case "-h":
    help();
    break;
  default:
    if (command) {
      console.error(`Unknown command: ${command}`);
      process.exit(1);
    }
    help();
    process.exit(0);
}
