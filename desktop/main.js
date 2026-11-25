const { app, BrowserWindow, Menu, shell, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

const ROOT_DIR = path.resolve(__dirname, "..");
const BACKEND_PORT = process.env.BACKEND_PORT || "8010";
const APP_URL = `http://127.0.0.1:${BACKEND_PORT}`;

let backendProc = null;
let mainWindow = null;

function getDataDir() {
  if (app.isPackaged) {
    const dir = path.join(app.getPath("userData"), "data");
    fs.mkdirSync(dir, { recursive: true });
    return dir;
  }
  return path.join(ROOT_DIR, "data");
}

function waitForHealth(url, retries = 80) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      http
        .get(url, (res) => {
          res.resume();
          if (res.statusCode === 200) return resolve();
          if (n <= 0) return reject(new Error(`Health check returned ${res.statusCode}`));
          setTimeout(() => attempt(n - 1), 400);
        })
        .on("error", () => {
          if (n <= 0) return reject(new Error(`Timeout waiting for ${url}`));
          setTimeout(() => attempt(n - 1), 400);
        });
    };
    attempt(retries);
  });
}

function startBackend() {
  const isWin = process.platform === "win32";
  const dataDir = getDataDir();

  if (app.isPackaged) {
    const backendExe = path.join(
      process.resourcesPath,
      "backend",
      isWin ? "jahtaria-backend.exe" : "jahtaria-backend"
    );
    const webuiDir = path.join(process.resourcesPath, "webui");
    const seedDataDir = path.join(process.resourcesPath, "seed-data");

    backendProc = spawn(backendExe, [], {
      cwd: path.dirname(backendExe),
      env: {
        ...process.env,
        BACKEND_HOST: "127.0.0.1",
        BACKEND_PORT,
        APP_ENV: "desktop",
        DATA_DIR: dataDir,
        BUNDLED_DATA_DIR: seedDataDir,
        STATIC_FRONTEND_DIR: webuiDir,
      },
      windowsHide: true,
      stdio: "ignore",
    });
  } else {
    const pyBin = isWin
      ? path.join(ROOT_DIR, "backend", ".venv", "Scripts", "uvicorn.exe")
      : path.join(ROOT_DIR, "backend", ".venv", "bin", "uvicorn");
    backendProc = spawn(pyBin, ["app.main:app", "--host", "127.0.0.1", "--port", BACKEND_PORT], {
      cwd: path.join(ROOT_DIR, "backend"),
      env: {
        ...process.env,
        DATA_DIR: dataDir,
        STATIC_FRONTEND_DIR: path.join(ROOT_DIR, "frontend", "out"),
      },
      windowsHide: true,
      stdio: "inherit",
    });
  }
}

function buildMenu() {
  const dataDir = getDataDir();
  const vaultDir = path.join(dataDir, "obsidian-vault");
  const template = [
    {
      label: "Jahtaria Suite",
      submenu: [
        {
          label: "Open Obsidian Vault Folder",
          click: () => {
            fs.mkdirSync(vaultDir, { recursive: true });
            shell.openPath(vaultDir);
          },
        },
        {
          label: "Open Local Data & PDFs Folder",
          click: () => shell.openPath(dataDir),
        },
        { type: "separator" },
        { role: "reload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1080,
    minHeight: 720,
    title: "Jahtaria Travel Services — U.S. Visa Intelligence Suite",
    icon: path.join(__dirname, "build", process.platform === "win32" ? "icon.ico" : "icon.png"),
    backgroundColor: "#0d0f13",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      plugins: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(APP_URL)) {
      return { action: "allow" };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });

  // Load dark graphite splash immediately while backend starts
  mainWindow.loadURL(
    "data:text/html;charset=utf-8," +
      encodeURIComponent(`
        <html><body style="margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:radial-gradient(ellipse at center,#182033 0%,#0d0f13 70%);color:#f1f5f9;font-family:Segoe UI,sans-serif;">
          <div style="font-size:22px;font-weight:700;color:#f1f5f9;letter-spacing:0.3px;">Jahtaria Visa Intelligence</div>
          <div style="font-size:13px;color:#9ca3af;margin-top:8px;">Starting AI Consular Agent...</div>
          <div style="margin-top:20px;width:180px;height:4px;background:rgba(255,255,255,0.12);border-radius:99px;overflow:hidden;">
            <div style="width:55%;height:100%;background:#60a5fa;border-radius:99px;"></div>
          </div>
        </body></html>
      `)
  );
}

app.whenReady().then(async () => {
  buildMenu();
  createWindow();
  startBackend();
  try {
    await waitForHealth(`${APP_URL}/health`, 90);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.loadURL(`${APP_URL}/login/`);
    }
  } catch (err) {
    dialog.showErrorBox(
      "Jahtaria Visa Intelligence Startup Error",
      `Could not start the local Visa Intelligence engine on port ${BACKEND_PORT}.\n\n${err.message}`
    );
  }
});

app.on("before-quit", () => {
  if (backendProc && !backendProc.killed) {
    backendProc.kill();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
