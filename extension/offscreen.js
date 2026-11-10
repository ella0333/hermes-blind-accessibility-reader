var queue = [];
var current = null;

function next() {
  if (current || !queue.length) { return; }
  current = queue.shift();
  var audio = new Audio(current.audio);
  current.el = audio;
  var finish = function (result) {
    var done = current;
    current = null;
    if (done) { done.reply(result); }
    next();
  };
  audio.onended = function () { finish({ ended: true }); };
  audio.onerror = function () { finish({ error: "could not play" }); };
  audio.play().catch(function (e) { finish({ error: String(e) }); });
}

var ctx = null;
function chime(kind) {
  ctx = ctx || new AudioContext();
  var now = ctx.currentTime;
  var notes = kind === "video" ? [523.25, 392.0] : [659.25, 880.0];
  notes.forEach(function (freq, i) {
    var o = ctx.createOscillator(), g = ctx.createGain(), t = now + i * 0.07;
    o.type = "sine"; o.frequency.value = freq;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.18, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    o.connect(g); g.connect(ctx.destination);
    o.start(t); o.stop(t + 0.13);
  });
}

chrome.runtime.onMessage.addListener(function (msg, sender, reply) {
  if (msg.target !== "offscreen") { return; }
  if (msg.type === "chime") { chime(msg.kind); reply({}); return; }
  if (msg.type === "play") {
    queue.push({ audio: msg.audio, reply: reply });
    next();
    return true;
  }
  if (msg.type === "stop") {
    queue.forEach(function (item) { item.reply({ stopped: true }); });
    queue = [];
    if (current) { current.el.pause(); var done = current; current = null; done.reply({ stopped: true }); }
    reply({});
  }
});
