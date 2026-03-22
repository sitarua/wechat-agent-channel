const { spawnSync, spawn } = require("child_process");
const path = require("path");

const scriptArg = process.argv[2];

if (!scriptArg) {
  console.error("Usage: node scripts/run-python.js <script> [args...]");
  process.exit(1);
}

const extraArgs = process.argv.slice(3);
const platform = process.platform;
const repoRoot = path.resolve(__dirname, "..");
const scriptPath = path.isAbsolute(scriptArg) ? scriptArg : path.resolve(repoRoot, scriptArg);

const candidates =
  platform === "win32"
    ? [
        ["py", ["-3"]],
        ["python", []],
        ["python3", []],
      ]
    : [
        ["python3", []],
        ["python", []],
      ];

function canRun(command, prefixArgs) {
  const result = spawnSync(command, [...prefixArgs, "--version"], {
    stdio: "ignore",
    windowsHide: true,
  });
  return !result.error && result.status === 0;
}

const selected = candidates.find(([command, prefixArgs]) => canRun(command, prefixArgs));

if (!selected) {
  const expected = platform === "win32" ? "py -3, python, or python3" : "python3 or python";
  console.error(`No supported Python interpreter found in PATH. Expected ${expected}.`);
  process.exit(1);
}

const [command, prefixArgs] = selected;
const child = spawn(command, [...prefixArgs, scriptPath, ...extraArgs], {
  stdio: "inherit",
  windowsHide: true,
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

child.on("error", (error) => {
  console.error(`Failed to start ${command}: ${error.message}`);
  process.exit(1);
});

["SIGINT", "SIGTERM"].forEach((signal) => {
  process.on(signal, () => {
    if (!child.killed) {
      child.kill(signal);
    }
  });
});
