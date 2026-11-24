const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

const ROOT_DIR = path.resolve(__dirname, "..");
const BACKEND_PORT = process.env.BACKEND_PORT || "8010";
const FRONTEND_PORT = process.env.FRONTEND_PORT || "3010";

let backendProc = null;
let frontendProc = null;
let mainWindow = null;

function waitForUrl(url, retries = 60) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      http
        .get(url, (res) => {
          res.resume();
          resolve();
        })
        .on("error", () => {
          if (n <= 0) return reject(new Error(`Timeout waiting for ${url}`));
          setTimeout(() => attempt(n - 1), 500);
        });
    };
    attempt(retries);
  });
}

function startServices() {
  const isWin = process.platform === "win32";
  const pyBin = isWin
    ? path.join(ROOT_DIR, "backend", ".venv", "Scripts", "uvicorn.exe")
    : path.join(ROOT_DIR, "backend", ".venv", "bin", "uvicorn");

  backendProc = spawn(pyBin, ["app.main:app", "--host", "127.0.0.1", "--port", BACKEND_PORT], {
    cwd: path.join(ROOT_DIR, "backend"),
    stdio: "inherit",
  });

  const npmCmd = isWin ? "npm.cmd" : "npm";
  frontendProc = spawn(npmCmd, ["run", "start", "--", "-p", FRONTEND_PORT], {
    cwd: path.join(ROOT_DIR, "frontend"),
    stdio: "inherit",
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1420,
    height: 920,
    minWidth: 1080,
    minHeight: 720,
    title: "Jahtaria Visa Intelligence & Document Automation",
    icon: path.join(__dirname, "build", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://localhost") || url.startsWith("http://127.0.0.1")) {
      return { action: "allow" };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.loadURL(`http://localhost:${FRONTEND_PORT}/login`);
}

app.whenReady().then(async () => {
  startServices();
  try {
    await waitForUrl(`http://127.0.0.1:${BACKEND_PORT}/health`, 60);
    await waitForUrl(`http://127.0.0.1:${FRONTEND_PORT}/login`, 60);
  } catch (err) {
    console.error("Service boot warning:", err);
  }
  createWindow();
});

app.on("before-quit", () => {
  if (backendProc) backendProc.kill();
  if (frontendProc) frontendProc.kill();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
