const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

function parseDotenv(dotenvPath) {
  if (!fs.existsSync(dotenvPath)) {
    return {};
  }

  const values = {};
  const lines = fs.readFileSync(dotenvPath, "utf8").split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) {
      continue;
    }

    const separatorIndex = line.indexOf("=");
    const key = line.slice(0, separatorIndex).trim();
    let value = line.slice(separatorIndex + 1).trim();

    if (
      value.length >= 2
      && ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }

    if (key) {
      values[key] = value;
    }
  }

  return values;
}

function isTruthyEnv(value) {
  if (value == null) {
    return false;
  }
  const normalized = String(value).trim().toLowerCase();
  return !["", "0", "false", "no", "off"].includes(normalized);
}

const rootDir = process.cwd();
const dotenvValues = parseDotenv(path.join(rootDir, ".env"));
const devHost = process.env.DEV_HOST || dotenvValues.DEV_HOST || "localhost";
const authApiBaseUrl = process.env.AUTH_API_BASE_URL || dotenvValues.AUTH_API_BASE_URL || "http://127.0.0.1:8000";
const orchestrationApiBaseUrl =
  process.env.ORCHESTRATION_API_BASE_URL
  || dotenvValues.ORCHESTRATION_API_BASE_URL
  || "http://127.0.0.1:8001";

const escapedAuthApiBaseUrl = authApiBaseUrl.replace(/'/g, "\\'");
const escapedOrchestrationApiBaseUrl = orchestrationApiBaseUrl.replace(/'/g, "\\'");

const args = [
  "serve",
  "--port",
  "3000",
  "--host",
  devHost,
  "--configuration",
  "development",
  `--define=AUTH_API_BASE_URL='${escapedAuthApiBaseUrl}'`,
  `--define=ORCHESTRATION_API_BASE_URL='${escapedOrchestrationApiBaseUrl}'`,
];

if (isTruthyEnv(process.env.DISABLE_HMR)) {
  args.push("--live-reload=false");
}

const ngEntrypoint = path.join(rootDir, "node_modules", "@angular", "cli", "bin", "ng.js");

const child = spawn(process.execPath, [ngEntrypoint, ...args], {
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code) => {
  process.exit(code ?? 1);
});

child.on("error", (error) => {
  console.error("Failed to run Angular dev server:", error.message);
  process.exit(1);
});
