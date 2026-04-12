import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

import { config as loadEnv } from "dotenv";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appDir = path.resolve(__dirname, "..");
const workspaceEnvPath = path.resolve(appDir, "../../.env");

if (existsSync(workspaceEnvPath)) {
  loadEnv({ path: workspaceEnvPath, override: false });
}

const nextBin = path.resolve(appDir, "node_modules/next/dist/bin/next");
const [, , ...nextArgs] = process.argv;
const [command] = nextArgs;

if (command === "dev" && !process.env.NEXT_DEV_POLL_INTERVAL) {
  process.env.NEXT_DEV_POLL_INTERVAL = "300";
}

const child = spawn(process.execPath, [nextBin, ...nextArgs], {
  cwd: appDir,
  env: process.env,
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
