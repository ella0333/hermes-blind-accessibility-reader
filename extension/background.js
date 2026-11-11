const API = "http://127.0.0.1:47823";
const OFFLINE = "Hermes isn't running, so the image and video reader can't describe anything yet. Open Hermes, then try again.";

async function call(path, body) {
  try {
    const res = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    return await res.json();
  } catch (e) {
    return { offline: true, error: OFFLINE };
  }
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let out = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    out += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(out);
}

async function blobToBase64(blob) {
  return toBase64(await blob.arrayBuffer());
}

async function capture(windowId, rect, dpr, maxSide) {
  const dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: "jpeg", quality: 80 });
  const blob = await (await fetch(dataUrl)).blob();
  const bmp = await createImageBitmap(blob);
  let sx = 0, sy = 0, sw = bmp.width, sh = bmp.height;
  if (rect) {
    sx = Math.max(0, Math.round(rect.x * dpr)); sy = Math.max(0, Math.round(rect.y * dpr));
    sw = Math.min(bmp.width - sx, Math.round(rect.width * dpr)); sh = Math.min(bmp.height - sy, Math.round(rect.height * dpr));
  }
  if (sw < 2 || sh < 2) { return null; }
  const scale = Math.min(1, maxSide / Math.max(sw, sh));
  const canvas = new OffscreenCanvas(Math.round(sw * scale), Math.round(sh * scale));
  canvas.getContext("2d").drawImage(bmp, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  return blobToBase64(await canvas.convertToBlob({ type: "image/jpeg", quality: 0.8 }));
}

async function fetchImage(src) {
  if (!/^https?:/.test(src || "")) { return ""; }
  try {
    const res = await fetch(src, { credentials: "omit" });
    if (!res.ok) { return ""; }
    const blob = await res.blob();
    if (blob.size > 12 * 1024 * 1024) { return ""; }
    return blobToBase64(blob);
  } catch (e) {
    return "";
  }
}

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) { return; }
  await chrome.offscreen.createDocument({ url: "offscreen.html", reasons: ["AUDIO_PLAYBACK"],
    justification: "Read image and video descriptions aloud in the voice the person chose." });
}

async function toOffscreen(message) {
  for (let attempt = 0; attempt < 8; attempt++) {
    try {
      await ensureOffscreen();
      return await chrome.runtime.sendMessage(Object.assign({ target: "offscreen" }, message));
    } catch (e) {
      await new Promise((r) => setTimeout(r, 250));
    }
  }
  return { error: "voice unavailable" };
}

function speakBrowserVoice(text) {
  return new Promise(function (resolve) {
    chrome.tts.speak(text, { enqueue: false, onEvent: function (e) {
      if (["end", "interrupted", "cancelled", "error"].indexOf(e.type) !== -1) { resolve({ ended: true }); }
    } });
  });
}

async function handle(msg, sender) {
  const windowId = sender.tab ? sender.tab.windowId : undefined;
  switch (msg.type) {
    case "api":
      return call(msg.path, msg.body);
    case "image": {
      let image = await fetchImage(msg.src);
      if (!image && msg.rect) { image = await capture(windowId, msg.rect, msg.dpr || 1, 768); }
      if (!image) { return { error: "Could not load that image." }; }
      return call("/image", { src: msg.src, image, alt: msg.alt, reason: msg.reason });
    }
    case "grab": {
      const image = await capture(windowId, msg.rect, msg.dpr || 1, msg.maxSide || 512);
      return { image: image || "" };
    }
    case "frame": {
      const image = await capture(windowId, msg.rect, msg.dpr || 1, 512);
      if (!image) { return {}; }
      return call(msg.single ? "/video/single" : "/video/frame", { video: msg.video, image });
    }
    case "play":
      if (sender.tab) { speakingTab = sender.tab.id; }
      return toOffscreen({ type: "play", audio: msg.audio });
    case "chime":
      return toOffscreen({ type: "chime", kind: msg.kind });
    case "tts":
      if (sender.tab) { speakingTab = sender.tab.id; }
      return speakBrowserVoice(msg.text);
    case "stop_audio":
      chrome.tts.stop();
      if (await chrome.offscreen.hasDocument()) { await chrome.runtime.sendMessage({ target: "offscreen", type: "stop" }).catch(() => {}); }
      return {};
    case "command":
      runCommand(msg.command);
      return {};
    case "screen": {
      const image = await capture(windowId, null, 1, 768);
      return call("/screen", { image, question: msg.question || "" });
    }
    default:
      return { error: "unknown message" };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  handle(msg, sender).then(reply, (e) => reply({ error: String(e) }));
  return true;
});

let speakingTab = null;
async function stopAll() {
  chrome.tts.stop();
  if (await chrome.offscreen.hasDocument()) {
    await chrome.runtime.sendMessage({ target: "offscreen", type: "stop" }).catch(() => {});
  }
}
chrome.tabs.onRemoved.addListener((tabId) => { if (tabId === speakingTab) { speakingTab = null; stopAll(); } });
chrome.tabs.onActivated.addListener((info) => { if (speakingTab !== null && info.tabId !== speakingTab) { speakingTab = null; stopAll(); } });

chrome.runtime.onInstalled.addListener(async () => {
  const tabs = await chrome.tabs.query({ url: ["http://*/*", "https://*/*"] });
  for (const tab of tabs) {
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] }).catch(() => {});
  }
});

const COMMANDS = { describe: "describe_now", price: "price_now", next: "next_item" };
chrome.commands.onCommand.addListener(async (command) => {
  if (!COMMANDS[command]) { return; }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.id) { chrome.tabs.sendMessage(tab.id, { type: COMMANDS[command] }).catch(() => {}); }
});

async function runCommand(cmd) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) { return call("/result", { id: cmd.id, text: "No browser tab is open." }); }
  const image = await capture(tab.windowId, null, 1, 768).catch(() => null);
  if (!image) { return call("/result", { id: cmd.id, text: "Could not capture the screen." }); }
  const res = await call("/screen", { image, question: cmd.question || "" });
  return call("/result", { id: cmd.id, text: res.text || res.error || "No description came back." });
}
