(function () {
  if (window.__bavirExt && window.__bavirExt === chrome.runtime.id + ":" + (chrome.runtime.getManifest().version)) { return; }
  window.__bavirExt = chrome.runtime.id + ":" + chrome.runtime.getManifest().version;
  document.querySelectorAll(".bavir-current, #bavir-caption, .bavir-live, button[data-bavir-for]").forEach(function (el) { el.remove(); });

  var MIN_SIZE = 64;
  var nextId = 1;
  var status = null;
  var offline = false;
  var tracked = {};
  var described = {};
  var narrating = null;
  var lastFocused = null;
  var JUNK_ALT = /^(image|img|photo|picture|graphic|figure|thumbnail|media|gif|video|embedded video|untitled|unknown|placeholder|loading)\b[\s\d.]*$/i;
  var FILE_ALT = /\.(jpe?g|png|gif|webp|avif|bmp|svg)(\?.*)?$/i;
  var VIDEO_HOSTS = /(youtube\.com\/embed|youtube-nocookie\.com|player\.vimeo\.com|player\.twitch\.tv|tiktok\.com\/embed|dailymotion\.com\/embed|streamable\.com)/i;

  var dead = false;
  function retire() {
    if (dead) { return; }
    dead = true;
    timers.forEach(clearInterval);
    document.querySelectorAll(".bavir-current, #bavir-caption, .bavir-live, button[data-bavir-for]").forEach(function (el) { el.remove(); });
  }
  var timers = [];
  function send(msg) {
    return new Promise(function (resolve) {
      if (dead || !chrome.runtime || !chrome.runtime.id) { retire(); resolve({}); return; }
      try { chrome.runtime.sendMessage(msg, function (res) { void chrome.runtime.lastError; resolve(res || {}); }); }
      catch (e) { retire(); resolve({}); }
    });
  }
  function api(path, body) { return send({ type: "api", path: path, body: body || {} }); }
  function settings() { return (status && status.settings) || {}; }
  function on() { return !offline && settings().enabled; }

  function judgeAlt(el) {
    if (el.dataset.bavirDone) { return "done"; }
    if (!el.hasAttribute("alt") && !el.getAttribute("aria-label")) { return "missing"; }
    var alt = (el.getAttribute("alt") || el.getAttribute("aria-label") || "").trim();
    if (alt === "") { return el.getAttribute("role") === "presentation" ? "decorative" : "missing"; }
    if (JUNK_ALT.test(alt) || FILE_ALT.test(alt) || /^[\w-]{20,}$/.test(alt)) { return "missing"; }
    if (/^r\/\w+ - /.test(alt)) { return "weak"; }
    if (alt.split(/\s+/).filter(Boolean).length <= 3) { return "weak"; }
    return "good";
  }
  function isTiny(el) { var r = el.getBoundingClientRect(); return r.width < MIN_SIZE || r.height < MIN_SIZE; }
  function inVideo(el) {
    var p = el.parentElement;
    for (var i = 0; i < 5 && p; i++, p = p.parentElement) { if (p.querySelector && p.querySelector("video")) { return true; } }
    return false;
  }
  function idFor(el) {
    if (!el.dataset.bavirId) { el.dataset.bavirId = String(nextId++); tracked[el.dataset.bavirId] = el; }
    return el.dataset.bavirId;
  }
  function viewRect(el) {
    var r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, width: r.width, height: r.height, visible: r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth };
  }
  function price(text) { return settings().readouts && text ? ", " + text : ""; }

  var live = null;
  var audio = null;
  var voiceQueue = [];
  var playing = false;
  function onScreen(el) {
    var r = el.getBoundingClientRect();
    var shown = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
    return shown > Math.min(r.height, innerHeight) * 0.5;
  }
  function announce(text, opts) {
    if (!text) { return; }
    text = text.replace(/^Description: /, "");
    opts = opts || {};
    if (opts.img && opts.img !== current) { return; }
    var out = settings().output || "screen_reader";
    if (out === "browser_voice" || out === "hermes_voice") {
      var item = { text: text, audio: null, failed: false, browser: out === "browser_voice", img: opts.img || null };
      if (opts.replace) { voiceQueue = []; }
      voiceQueue.push(item);
      if (item.browser) { playNext(); return; }
      api("/speak", { text: text }).then(function (res) {
        if (res.audio) { item.audio = res.audio; } else { item.failed = true; }
        playNext();
      });
      return;
    }
    showCaption(text);
    liveSay(text);
    if (opts.img) {
      speakingFor = opts.img;
      clearTimeout(announce.until);
      announce.until = setTimeout(function () { if (speakingFor === opts.img) { speakingFor = null; } }, 1500 + text.length * 65);
    }
  }
  function playNext() {
    if (playing || !voiceQueue.length) { return; }
    var item = voiceQueue[0];
    if (!item.browser && !item.audio && !item.failed) { return; }
    voiceQueue.shift();
    if (item.img && item.img !== current) { playNext(); return; }
    if (item.failed) { showCaption(item.text); liveSay(item.text); playNext(); return; }
    playing = true;
    speakingFor = item.img || null;
    showCaption(item.text);
    var msg = item.browser ? { type: "tts", text: item.text } : { type: "play", audio: item.audio };
    send(msg).then(function () { playing = false; if (speakingFor === item.img) { speakingFor = null; } playNext(); });
  }
  function liveHome() {
    var dialogs = document.querySelectorAll('[aria-modal="true"], dialog[open]');
    for (var i = dialogs.length - 1; i >= 0; i--) {
      var r = dialogs[i].getBoundingClientRect();
      if (r.width > 0 && r.height > 0) { return dialogs[i]; }
    }
    return document.body;
  }
  function ensureLive() {
    var home = liveHome();
    if (live && live.parentElement === home) { return false; }
    if (!live) {
      live = document.createElement("div");
      live.className = "bavir-live";
      live.setAttribute("role", "status");
      live.setAttribute("aria-live", "polite");
      live.setAttribute("aria-atomic", "true");
      live.style.cssText = "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;";
    }
    live.textContent = "";
    home.appendChild(live);
    return true;
  }
  function liveSay(text) {
    var fresh = ensureLive();
    live.textContent = "";
    setTimeout(function () { live.textContent = text; }, fresh ? 400 : 60);
  }
  function stopSpeech() {
    voiceQueue = [];
    playing = false;
    send({ type: "stop_audio" });
  }
  function sayResult(res) {
    if (res.spent) { setSpent(res.spent); }
    if (res.error) { announce(res.error); return; }
    if (res.text) { announce(res.text); }
    if (res.warning) { setTimeout(function () { announce(res.warning); }, 4000); }
  }

  function captionsOn() { return !!settings().captions; }
  var style = null, bar = null, barText = null, barSpent = null;
  function ensureStyle() {
    if (style && document.documentElement.contains(style)) { return; }
    style = document.createElement("style");
    var mine = chrome.runtime.getManifest().version;
    style.textContent =
      ".bavir-current:not([data-v='" + mine + "']),#bavir-caption:not([data-v='" + mine + "']){display:none!important}" +
      ".bavir-current{position:fixed;z-index:2147483640;pointer-events:none;border:3px solid #3b82f6;border-radius:10px;box-shadow:0 0 0 2px rgba(255,255,255,.7)}" +
      ".bavir-current.busy{border-style:dashed}" +
      "#bavir-caption{position:fixed;z-index:2147483641;left:50%;bottom:6vh;transform:translateX(-50%);max-width:min(70vw,900px);box-sizing:border-box;" +
      "background:rgba(8,8,8,.72);color:#fff;border-radius:6px;padding:6px 14px;font:500 20px/1.4 system-ui,sans-serif;text-align:center;pointer-events:none;" +
      "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;transition:opacity .4s}" +
      "#bavir-caption.idle{opacity:0}" +
      "#bavir-caption .bavir-spent{display:none}";
    document.documentElement.appendChild(style);
  }
  function showCaption(text) {
    if (!captionsOn()) { return; }
    ensureStyle();
    if (!bar || !document.body.contains(bar)) {
      bar = document.createElement("div"); bar.id = "bavir-caption"; bar.setAttribute("aria-hidden", "true");
      bar.dataset.v = chrome.runtime.getManifest().version;
      barText = document.createElement("span"); barSpent = document.createElement("span"); barSpent.className = "bavir-spent";
      bar.appendChild(barText); bar.appendChild(barSpent); document.body.appendChild(bar);
    }
    barText.textContent = text.replace(/^Description: /, "");
    bar.classList.remove("idle");
    clearTimeout(showCaption.timer);
    showCaption.timer = setTimeout(function () { if (bar) { bar.classList.add("idle"); } }, 3500 + text.length * 45);
  }
  function setSpent(text) {
    if (status) { status.spent_short = text; }
    if (barSpent) { barSpent.textContent = text; }
  }
  var current = null, curRing = null, curBusy = false;
  var speakingFor = null;
  function active() {
    return curBusy || (speakingFor && speakingFor === current) || (narrating && narrating.el === current);
  }
  function drawCurrent() {
    if (!current || !on() || !document.body.contains(current)) { if (curRing) { curRing.style.display = "none"; } return; }
    ensureStyle();
    if (!curRing || !document.body.contains(curRing)) {
      curRing = document.createElement("div"); curRing.className = "bavir-current"; curRing.setAttribute("aria-hidden", "true");
      curRing.dataset.v = chrome.runtime.getManifest().version;
      document.body.appendChild(curRing);
    }
    var b = current.getBoundingClientRect();
    if (b.width < 2 && current.parentElement) { b = current.parentElement.getBoundingClientRect(); }
    curRing.classList.toggle("busy", curBusy);
    curRing.style.left = (b.left - 5) + "px"; curRing.style.top = (b.top - 5) + "px";
    curRing.style.width = (b.width + 10) + "px"; curRing.style.height = (b.height + 10) + "px";
    curRing.style.display = b.bottom < 0 || b.top > innerHeight ? "none" : "block";
  }
  (function ringLoop() { drawCurrent(); requestAnimationFrame(ringLoop); })();
  function markImage(img, state) {
    if (img === current) { curBusy = state === "busy"; }
  }

  function grab(rect, maxSide) {
    var hidden = [];
    if (bar) { hidden.push(bar); }
    if (curRing) { hidden.push(curRing); }
    hidden.forEach(function (el) { el.style.visibility = "hidden"; });
    return new Promise(function (resolve) {
      requestAnimationFrame(function () { setTimeout(function () {
        send({ type: "grab", rect: rect, dpr: devicePixelRatio || 1, maxSide: maxSide }).then(function (res) {
          hidden.forEach(function (el) { el.style.visibility = ""; });
          resolve(res.image || "");
        });
      }, 40); });
    });
  }
  function clearCaptions() {
    if (bar) { bar.remove(); bar = null; }
  }

  var HIDDEN = "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0;padding:0;";
  function buttonFor(img, verdict) {
    var anchor = img.closest("a") || img;
    var existing = anchor.nextElementSibling;
    if (existing && existing.dataset && existing.dataset.bavirFor === img.dataset.bavirId) { return existing; }
    var btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.bavirFor = img.dataset.bavirId;
    btn.style.cssText = HIDDEN;
    btn.addEventListener("focus", function () { btn.style.cssText = "position:relative;z-index:2147483646;font:14px sans-serif;padding:4px 8px;margin:4px;border-radius:6px;border:2px solid #1d4ed8;background:#fff;color:#111;"; });
    btn.addEventListener("blur", function () { btn.style.cssText = HIDDEN; });
    btn.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      describeImage(img, judgeAlt(img) === "weak" ? "improve" : "add");
    }, true);
    anchor.insertAdjacentElement("afterend", btn);
    return btn;
  }
  function labelButton(btn, verdict) {
    var text = verdict === "weak" ? "Alt text may be weak. Improve description" : "No description. Add one";
    text += price(status && status.image_text);
    if (btn.textContent !== text && btn.dataset.busy !== "1") { btn.textContent = text; }
  }

  function applyAlt(el, full) {
    el.setAttribute("alt", full);
    el.dataset.bavirDone = "1";
    var holder = el.parentElement;
    for (var i = 0; i < 4 && holder; i++, holder = holder.parentElement) {
      var label = holder.getAttribute && holder.getAttribute("aria-label");
      if (label && (JUNK_ALT.test(label.trim()) || label.indexOf("Description: ") === 0)) {
        holder.setAttribute("role", "img");
        holder.setAttribute("aria-label", full);
        el.setAttribute("aria-hidden", "true");
        break;
      }
    }
    var anchor = el.closest("a") || el;
    var btn = anchor.nextElementSibling;
    if (btn && btn.dataset && btn.dataset.bavirFor === el.dataset.bavirId) { btn.remove(); }
  }

  var inFlight = {};
  function describeImage(img, reason, quiet) {
    if (!quiet && img !== current) { setCurrent(img); }
    var flightKey = (img.currentSrc || img.src || "") + "|" + reason;
    if (inFlight[flightKey]) { if (!quiet) { inFlight[flightKey].speak = true; inFlight[flightKey].img = img; } return; }
    if (offline) { announce("Hermes isn't running, so the image and video reader can't describe anything yet. Open Hermes, then try again."); return; }
    var id = idFor(img);
    var anchor = img.closest("a") || img;
    var btn = anchor.nextElementSibling;
    var hasButton = btn && btn.dataset && btn.dataset.bavirFor === id;
    if (hasButton) { btn.dataset.busy = "1"; btn.textContent = "Describing image"; }
    else if (!quiet && settings().output === "screen_reader") { announce("Describing image."); }
    var original = (img.getAttribute("alt") || "").trim();
    markImage(img, "busy");
    var flight = inFlight[flightKey] = { speak: !quiet, img: img };
    send({ type: "image", src: img.currentSrc || img.src || "", alt: original, reason: reason,
           rect: viewRect(img), dpr: devicePixelRatio || 1 }).then(function (res) {
      if (btn) { btn.dataset.busy = ""; }
      delete inFlight[flightKey];
      var speakIt = flight.speak;
      if (res.spent) { setSpent(res.spent); }
      if (res.error || !res.text) { if (speakIt) { sayResult(res); } return; }
      markImage(img, "done");
      var keep = reason === "improve" && original && !JUNK_ALT.test(original) ? " Original alt text: " + original : "";
      var full = "Description: " + res.text + keep;
      applyAlt(img, full);
      if (img.currentSrc || img.src) { described[img.currentSrc || img.src] = full; }
      if (speakIt) { announce(full, { img: img }); }
      if (res.warning) { setTimeout(function () { announce(res.warning); }, 4000); }
    });
  }

  function durationKnown(v) { return v.tagName === "VIDEO" && isFinite(v.duration) && v.duration > 0; }
  function videoKey(v) { return location.href.split("#")[0] + "#" + idFor(v); }
  function offerNarration(v) {
    if (!on() || !v || v.tagName !== "VIDEO" || isTiny(v) || v.dataset.bavirOffered) { return; }
    if (v.muted) { return; }
    if (narrating && narrating.id === idFor(v)) { return; }
    v.dataset.bavirOffered = "1";
    api("/video/offer", { seconds: durationKnown(v) ? v.duration : null }).then(function (res) { if (res.text) { announce(res.text); } });
  }
  document.addEventListener("play", function (e) { offerNarration(e.target); }, true);
  document.addEventListener("volumechange", function (e) { if (e.target && !e.target.paused) { offerNarration(e.target); } }, true);
  document.addEventListener("pause", function (e) {
    var v = e.target;
    if (!narrating || !v || !v.dataset || v.dataset.bavirId !== narrating.id) { return; }
    setTimeout(function () { if (narrating && narrating.el === v && v.paused) { stopSpeech(); } }, 1500);
  }, true);
  document.addEventListener("ended", function (e) {
    var v = e.target;
    if (!narrating || !v || !v.dataset || v.dataset.bavirId !== narrating.id) { return; }
    finishNarration();
  }, true);

  function deepAll(selector) {
    var out = Array.prototype.slice.call(document.querySelectorAll(selector));
    var roots = [document];
    while (roots.length) {
      var all = roots.pop().querySelectorAll("*");
      for (var i = 0; i < all.length; i++) {
        var sr = all[i].shadowRoot;
        if (sr) { out.push.apply(out, sr.querySelectorAll(selector)); roots.push(sr); }
      }
    }
    return out;
  }
  function targetVideo() {
    var vids = deepAll("video"), best = null, area = 0;
    for (var i = 0; i < vids.length; i++) {
      var v = vids[i];
      if (!v.paused && !v.ended && v.readyState > 2 && !isTiny(v) && viewRect(v).visible) { return v; }
    }
    if (lastFocused && (lastFocused.tagName === "VIDEO" || (lastFocused.tagName === "IFRAME" && VIDEO_HOSTS.test(lastFocused.src || "")))) { return lastFocused; }
    for (var j = 0; j < vids.length; j++) {
      var r = viewRect(vids[j]);
      if (r.visible && !isTiny(vids[j]) && r.width * r.height > area) { best = vids[j]; area = r.width * r.height; }
    }
    return best;
  }

  function startNarration(v) {
    var id = idFor(v), key = videoKey(v);
    api("/video/start", { video: key, seconds: durationKnown(v) ? v.duration : null }).then(function (res) {
      if (res.offline) { sayResult(res); return; }
      if (settings().mode !== "auto") { announce(res.text || "Narrating."); }
      narrating = { id: id, key: key, el: v, startedAt: Date.now() };
      narrating.timer = setInterval(function () { narrationTick(); }, 3000);
      narrationTick();
    });
  }
  function stopNarration(say) {
    if (!narrating) { return; }
    clearInterval(narrating.timer);
    api("/video/stop", { video: narrating.key });
    narrating = null;
    stopSpeech();
    if (say) { announce("Narration off."); }
  }
  var told = {};
  function videoMemoryKey(v) {
    return (v.poster || "") + "|" + location.pathname + location.search + "|" + (durationKnown(v) ? Math.round(v.duration) : "live");
  }
  function rememberLine(v, t, text) {
    var k = videoMemoryKey(v);
    (told[k] = told[k] || []).push({ t: t, text: text });
  }
  function recallLine(v) {
    var lines = told[videoMemoryKey(v)];
    if (!lines || v.tagName !== "VIDEO") { return null; }
    var t = v.currentTime, best = null;
    lines.forEach(function (l) { if (l.t <= t + 0.5 && t - l.t < 3 && (!best || l.t > best.t)) { best = l; } });
    if (!best || narrating.lastRecalled === best) { return best ? "same" : null; }
    narrating.lastRecalled = best;
    return best;
  }
  function finishNarration() {
    if (!narrating) { return; }
    clearInterval(narrating.timer);
    api("/video/stop", { video: narrating.key });
    narrating = null;
  }
  function playedThrough(v) {
    if (v.tagName !== "VIDEO" || !durationKnown(v) || !narrating.startedAt) { return false; }
    return (Date.now() - narrating.startedAt) / 1000 >= v.duration + 0.5;
  }
  var ticking = false;
  function narrationTick() {
    if (!narrating || ticking) { return; }
    var v = narrating.el;
    if (!document.body.contains(v)) { stopNarration(false); return; }
    if (playedThrough(v)) { finishNarration(); return; }
    if (v.tagName === "VIDEO" && (v.paused || v.ended)) { return; }
    var r = viewRect(v);
    if (!r.visible || document.visibilityState !== "visible") { return; }
    var known = recallLine(v);
    if (known === "same") { return; }
    if (known) { announce(known.text, { replace: true, img: v }); return; }
    ticking = true;
    var key = narrating.key, at = v.tagName === "VIDEO" ? v.currentTime : 0, vid = v;
    grab(r, 512).then(function (image) {
      if (!image) { return {}; }
      return api("/video/frame", { video: key, image: image });
    }).then(function (res) {
      res = res || {};
      ticking = false;
      if (res.spent) { setSpent(res.spent); }
      if (res.text) {
        announce(res.text, { replace: true, img: vid });
        if (!res.stop) { rememberLine(vid, at, res.text); }
      }
      if (res.warning) { setTimeout(function () { announce(res.warning); }, 4000); }
      if (res.stop) { if (narrating) { clearInterval(narrating.timer); narrating = null; } }
    });
  }

  document.addEventListener("focusin", function (e) { lastFocused = e.target; }, true);
  function describeNow() {
    if (offline) { announce("Hermes isn't running, so the image and video reader can't describe anything yet. Open Hermes, then try again."); return; }
    if (!settings().enabled) { announce("The image and video reader is off. Press Alt+Shift+S to open its settings and turn it on."); return; }
    var focused = document.activeElement;
    if (focused && focused.dataset && focused.dataset.bavirFor && tracked[focused.dataset.bavirFor]) { setCurrent(tracked[focused.dataset.bavirFor]); }
    else if (focused && focused.tagName === "IMG" && !isTiny(focused)) { setCurrent(focused); }
    if (!current || !document.body.contains(current) || !viewRect(current).visible) {
      var c = nearestCenter();
      if (!c) {
        if (settings().output === "screen_reader") { announce("Describing the screen."); }
        grab(null, 768).then(function (image) { return api("/screen", { image: image }); }).then(sayResult);
        return;
      }
      setCurrent(c);
    }
    var el = current;
    if (el.tagName === "VIDEO") {
      if (narrating && narrating.id === idFor(el)) { stopNarration(true); return; }
      if (el.paused) {
        grab(viewRect(el), 512).then(function (image) { return api("/video/single", { image: image }); }).then(sayResult);
        return;
      }
      startNarration(el);
      return;
    }
    if (el.dataset.bavirDone) { announce(el.getAttribute("alt") || ""); return; }
    describeImage(el, judgeAlt(el) === "weak" ? "improve" : "add");
  }
  function priceNow() {
    if (offline) { announce("Hermes isn't running, so the reader can't check prices right now."); return; }
    var v = targetVideo();
    var body = v ? { kind: "video", seconds: durationKnown(v) ? v.duration : null } : { kind: "image" };
    api("/price", body).then(function (res) { if (res.text) { announce(res.text, { replace: true }); } });
  }
  var lastMove = 0;
  function items() {
    return deepAll("img, video").filter(function (el) {
      if (isTiny(el)) { return false; }
      if (el.tagName === "IMG" && (inVideo(el) || judgeAlt(el) === "decorative" ||
          (el.getAttribute("aria-hidden") === "true" && !el.closest("a,[aria-label]") && !el.dataset.bavirDone))) { return false; }
      return true;
    });
  }
  function pageTop(el) { return el.getBoundingClientRect().top + scrollY; }
  function nearestCenter() {
    var best = null, dist = Infinity, mid = innerHeight / 2;
    items().forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (!onScreen(el)) { return; }
      var d = Math.abs((r.top + r.bottom) / 2 - mid);
      if (d < dist) { best = el; dist = d; }
    });
    return best;
  }
  var arrivedAs = "";
  function identity(el) { return location.href + "|" + (el.currentSrc || el.src || ""); }
  function setCurrent(el) {
    var moved = current !== el || identity(el) !== arrivedAs;
    if (moved) {
      if (narrating) { stopNarration(false); }
      stopSpeech();
    }
    current = el; curBusy = false; lastFocused = el; idFor(el);
    arrivedAs = identity(el);
    if (moved && settings().chime) { send({ type: "chime", kind: el.tagName === "VIDEO" ? "video" : "image" }); }
  }
  function arrive(el) {
    var st = settings(), auto = st.mode === "auto";
    if (el.tagName === "VIDEO") {
      var label = st.read_titles ? videoLabel(el) : "";
      if (label) { announce(label, { img: el }); }
      if (auto) { startNarration(el); }
      else if (!label) { announce(durationKnown(el) ? "Video, " + spokenDuration(el.duration) + "." : "Video.", { img: el }); }
      return;
    }
    if (el.dataset.bavirDone) { announce(el.getAttribute("alt") || "", { img: el }); return; }
    var verdict = judgeAlt(el);
    var own = (el.getAttribute("alt") || el.getAttribute("aria-label") || "").trim();
    if (verdict === "good" && !st.replace_alt) { if (st.read_titles || st.output !== "screen_reader") { announce(own, { img: el }); } return; }
    if (st.read_titles && own && verdict !== "missing") { announce(own, { img: el }); }
    if (auto) { describeImage(el, own && verdict !== "missing" ? "improve" : "add"); return; }
    if (!st.read_titles || verdict === "missing") { announce(verdict === "missing" ? "Image without a description." : "Image with a short caption: " + own); }
  }
  function videoLabel(v) {
    var own = (v.getAttribute("aria-label") || v.getAttribute("title") || "").trim();
    if (own && !JUNK_ALT.test(own)) { return clip(own); }
    var post = v.closest("article");
    var text = post && post.querySelector('[data-testid="tweetText"], [lang]');
    if (text && text.innerText.trim()) { return clip(text.innerText.trim()); }
    if (/youtube\.com\/(watch|shorts)/.test(location.href)) { return clip(document.title.replace(/ - YouTube$/, "").replace(/#\S+/g, "").trim()); }
    return "";
  }
  function clip(t) { return t.length > 160 ? t.slice(0, 157).replace(/\s+\S*$/, "") + "..." : t; }
  function spokenDuration(sec) {
    if (sec < 60) { var s0 = Math.max(1, Math.round(sec)); return s0 + (s0 === 1 ? " second" : " seconds"); }
    var m = Math.round(sec / 60); return m + (m === 1 ? " minute" : " minutes");
  }
  function nextItem() {
    if (!on()) { describeNow(); return; }
    var list = items().sort(function (a, b) { return pageTop(a) - pageTop(b); });
    if (!list.length) { announce("No images or videos on this page."); return; }
    var from = current && document.body.contains(current) ? pageTop(current) + 2 : scrollY + innerHeight * 0.1;
    var next = list.filter(function (el) { return pageTop(el) > from; })[0];
    if (!next) { next = list[0]; announce("Back to the first one."); }
    setCurrent(next);
    lastMove = Date.now();
    next.scrollIntoView({ block: "center", behavior: "smooth" });
    setTimeout(function () { arrive(next); }, 350);
  }
  function priceNow() {
    if (offline) { announce("Hermes isn't running, so the reader can't check prices right now."); return; }
    var v = current && current.tagName === "VIDEO" ? current : null;
    var body = v ? { kind: "video", seconds: durationKnown(v) ? v.duration : null } : { kind: "image" };
    api("/price", body).then(function (res) { if (res.text) { announce(res.text, { replace: true }); } });
  }
  function introOnce() {
    var today = new Date().toDateString();
    try {
      chrome.storage.local.get("introDay", function (v) {
        if (v && v.introDay === today) { return; }
        chrome.storage.local.set({ introDay: today });
        announce("Image and video reader on. Alt+Shift+Period moves to the next image or video. Alt+Shift+D describes it, or starts and stops a video's narration.");
      });
    } catch (e) {}
  }
  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg.type === "price_now") { priceNow(); }
    if (msg.type === "next_item") { nextItem(); }
    if (msg.type === "describe_now") { describeNow(); }
    if (msg.type === "refresh") { refresh(msg.announce); }
  });

  var lastDeep = 0, images = [], videos = [];
  function scan() {
    if (!on()) { return; }
    if (Date.now() - lastDeep > 2500) { images = deepAll("img"); videos = deepAll("video"); lastDeep = Date.now(); }
    for (var j = 0; j < videos.length; j++) {
      if (!videos[j].paused && !videos[j].ended) { offerNarration(videos[j]); }
    }
    var auto = settings().mode === "auto";
    for (var i = 0; i < images.length; i++) {
      var img = images[i];
      if (img.dataset.bavirDone || isTiny(img)) { continue; }
      var known = described[img.currentSrc || img.src];
      if (known) { idFor(img); applyAlt(img, known); continue; }
      if (img.getAttribute("aria-hidden") === "true" && !img.closest("a,[aria-label]")) { continue; }
      if (inVideo(img)) { continue; }
      var verdict = judgeAlt(img);
      if (verdict === "good" || verdict === "decorative" || verdict === "done") { continue; }
      idFor(img);
      if (verdict === "missing" && auto && settings().output === "screen_reader" && !captionsOn()) {
        var r = img.getBoundingClientRect();
        if (r.bottom > -innerHeight && r.top < innerHeight * 2 && !img.dataset.bavirQueued) {
          img.dataset.bavirQueued = "1";
          describeImage(img, "add", true);
        }
        continue;
      }
      labelButton(buttonFor(img, verdict), verdict);
    }
  }
  var settleOn = null, settleSince = 0;
  function followCenter() {
    if (!on() || Date.now() - lastMove < 1500) { return; }
    var auto = settings().mode === "auto";
    if (narrating && current && document.body.contains(current) && onScreen(current) && identity(current) === arrivedAs) { return; }
    var c = nearestCenter();
    if (c && c === current && identity(c) !== arrivedAs) {
      if (narrating) { stopNarration(false); }
      setCurrent(c); if (auto) { arrive(c); } return;
    }
    if (!c || c === current) { settleOn = null; return; }
    if (c !== settleOn) { settleOn = c; settleSince = Date.now(); return; }
    if (Date.now() - settleSince < 500) { return; }
    settleOn = null;
    setCurrent(c); if (auto) { arrive(c); }
  }
  function removeButtons() {
    document.querySelectorAll("button[data-bavir-for]").forEach(function (b) { b.remove(); });
  }

  function refresh(sayIt) {
    return api("/status").then(function (res) {
      offline = !!res.offline;
      if (!offline && !res.error) { status = res; }
      if (!on()) { removeButtons(); }
      if (!on() || !captionsOn()) { clearCaptions(); }
      if (sayIt && status) { announce(status.on_message); }
      if (on() && status) { introOnce(); }
    });
  }

  timers.push(setInterval(function () {
    if (document.visibilityState !== "visible" || offline) { return; }
    api("/tick").then(function (res) {
      if (res.offline) { offline = true; return; }
      if (res.command) { send({ type: "command", command: res.command }); }
    });
  }, 2000));
  timers.push(setInterval(function () { if (offline) { refresh(false); } }, 3000));
  timers.push(setInterval(function () { if (!offline) { refresh(false); } }, 15000));
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { if (narrating) { stopNarration(false); } else { stopSpeech(); } }
  });
  timers.push(setInterval(scan, 1000));
  timers.push(setInterval(function () { if (on()) { ensureLive(); } }, 1000));
  timers.push(setInterval(followCenter, 250));
  timers.push(setInterval(function () { if (narrating && narrating.el && document.body.contains(narrating.el) && playedThrough(narrating.el)) { finishNarration(); } }, 400));
  refresh(false).then(scan);
})();
