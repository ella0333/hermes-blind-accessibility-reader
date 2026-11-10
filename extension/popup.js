var form = document.getElementById("form");
var message = document.getElementById("message");
var state = null;

function api(path, body) {
  return new Promise(function (resolve) {
    chrome.runtime.sendMessage({ type: "api", path: path, body: body || {} }, function (res) { resolve(res || {}); });
  });
}

function say(text) {
  message.textContent = "";
  setTimeout(function () { message.textContent = text; }, 60);
}

function fill(s) {
  state = s;
  var st = s.settings;
  clearConfirm("confirm-wrap");
  clearConfirm("mode-confirm");
  ["enabled", "readouts", "captions", "chime", "read_titles", "replace_alt"].forEach(function (name) {
    var box = form.elements[name];
    if (box) { box.checked = !!st[name]; }
  });
  form.ceiling.value = st.ceiling;
  if (form.elements.video_cap) { form.elements.video_cap.value = st.video_cap; }
  form.querySelectorAll("input[name=mode]").forEach(function (r) { r.checked = r.value === st.mode; });
  form.querySelectorAll("input[name=output]").forEach(function (r) { r.checked = r.value === st.output; });
  document.getElementById("auto-label").textContent =
    "Auto. Describes each image as you reach it, " + s.image_text + " each, and narrates each video, stopping at its estimate.";
  document.getElementById("spent").textContent = s.spent_text + " " + s.price_line;
  var box = document.getElementById("models");
  var existing = box.querySelectorAll("input[name=model]");
  var same = existing.length === s.models.length && s.models.every(function (m, i) { return existing[i].value === m.id; });
  if (same) {
    s.models.forEach(function (m, i) {
      existing[i].checked = m.id === st.model;
      existing[i].nextSibling.textContent = " " + m.label;
    });
    return;
  }
  box.querySelectorAll("label").forEach(function (l) { l.remove(); });
  s.models.forEach(function (m) {
    var label = document.createElement("label");
    var input = document.createElement("input");
    input.type = "radio"; input.name = "model"; input.value = m.id; input.checked = m.id === st.model;
    label.appendChild(input);
    label.appendChild(document.createTextNode(" " + m.label));
    box.appendChild(label);
  });
}

function clearConfirm(id) {
  document.getElementById(id).textContent = "";
}

function confirmFirst(id, radio, buttonText, spoken, onConfirm) {
  var wrap = document.getElementById(id);
  wrap.textContent = "";
  var b = document.createElement("button");
  b.type = "button";
  b.textContent = buttonText;
  b.addEventListener("click", function () { radio.focus(); wrap.textContent = ""; onConfirm(); });
  var p = document.createElement("p");
  p.appendChild(b);
  wrap.appendChild(p);
  say(spoken);
}

function tellTabs(announce) {
  chrome.tabs.query({}, function (tabs) {
    tabs.forEach(function (t) { if (t.id) { chrome.tabs.sendMessage(t.id, { type: "refresh", announce: announce }).catch(function () {}); } });
  });
}

function save(key, value) {
  return api("/settings", { key: key, value: value }).then(function (res) {
    if (res.offline || res.error) { say(res.error || "Could not save that."); return; }
    fill(res.status);
    say(res.message);
    if (!res.status.settings.setup_done) { api("/settings", { key: "setup_done", value: true }); }
    tellTabs(false);
  });
}

form.addEventListener("submit", function (e) { e.preventDefault(); });
form.addEventListener("change", function (e) {
  var t = e.target;
  if (["enabled", "readouts", "captions", "chime", "read_titles", "replace_alt"].indexOf(t.name) !== -1) { save(t.name, t.checked); return; }
  if (t.name === "ceiling" || t.name === "video_cap") { save(t.name, parseFloat(t.value) || 0); return; }
  if (t.name === "model") {
    var m = state.models.filter(function (x) { return x.id === t.value; })[0];
    if (m && m.expensive) {
      confirmFirst("confirm-wrap", t, "Confirm switch to " + m.short + ". Up to " + m.hour_text + " for an hour of busy video.",
        m.short + " costs up to " + m.hour_text + " for an hour of busy video. Press Tab to reach the confirm button, or pick another model.",
        function () { save("model", m.id); });
      return;
    }
    clearConfirm("confirm-wrap");
    save("model", t.value);
    return;
  }
  if (t.name === "mode") {
    if (t.value === "auto") {
      confirmFirst("mode-confirm", t, "Confirm auto mode. " + state.image_text + " per image.",
        "Auto describes each image as you reach it, " + state.image_text + " each, and narrates each video. " + state.spent_text +
        " Press Tab to reach the confirm button, or stay on manual.",
        function () { save("mode", "auto"); });
      return;
    }
    clearConfirm("mode-confirm");
  }
  save(t.name, t.value);
});

api("/status").then(function (res) {
  if (res.offline || res.error) {
    document.getElementById("offline").hidden = false;
    say(res.error || "Hermes isn't running.");
    return;
  }
  form.hidden = false;
  fill(res);
  var first = form.querySelector("input");
  first.focus();
  if (!res.settings.setup_done) {
    say("Welcome. Choose a model and a daily ceiling, then turn describing on. Every price is listed next to its option.");
  } else {
    say(res.on_message);
  }
});
