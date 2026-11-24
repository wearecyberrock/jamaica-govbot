const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("jahtariaDesktop", {
  platform: process.platform,
  version: "1.0.0",
});
