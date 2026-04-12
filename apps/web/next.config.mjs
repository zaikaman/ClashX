import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pollIntervalMs = Number.parseInt(process.env.NEXT_DEV_POLL_INTERVAL ?? "", 10);
const watchOptions =
  Number.isFinite(pollIntervalMs) && pollIntervalMs > 0
    ? { pollIntervalMs }
    : undefined;

/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: {
    root: __dirname,
  },
  watchOptions,
};

export default nextConfig;
