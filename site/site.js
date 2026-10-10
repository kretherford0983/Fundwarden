// pennywarden.org (1.10.0, #83): download buttons from releases.json, the visitor's system highlighted.
// Plain DOM: data from the file is only ever set with textContent and checked attributes, never parsed as markup.
(function () {
  "use strict";
  function detectOs() {
    var ua = (navigator.userAgent || "").toLowerCase();
    var plat = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "").toLowerCase();
    if (plat.indexOf("win") === 0 || ua.indexOf("windows") >= 0) return "windows";
    if (plat.indexOf("mac") === 0 || ua.indexOf("mac os x") >= 0) return "mac";
    if (ua.indexOf("linux") >= 0 && ua.indexOf("android") < 0) return "linux";
    return null;
  }
  function size(n) { return n ? (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB" : ""; }
  function safeUrl(u) { return typeof u === "string" && u.indexOf("https://github.com/") === 0 ? u : null; }

  var os = detectOs();
  if (os) {
    var card = document.querySelector('.card[data-os="' + os + '"]');
    if (card) {
      card.classList.add("yours");
      var tag = document.createElement("span");
      tag.className = "yours-tag";
      tag.textContent = "Your system";
      card.insertBefore(tag, card.firstChild);
      var btn = card.querySelector(".button");
      if (btn) btn.classList.add("primary");
    }
  }

  fetch("releases.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
    var line = document.getElementById("release-line");
    if (!d || !d.releases || !d.releases.length) { line.textContent = "See the latest release on GitHub."; return; }
    var rel = d.releases[0];
    line.textContent = "Current release: " + rel.version + " — " + rel.date + ". ";
    var notes = document.createElement("a");
    notes.textContent = "What's new";
    if (safeUrl(rel.url)) notes.href = rel.url;
    line.appendChild(notes);
    document.getElementById("hero-version").textContent = "Version " + rel.version + " · " + rel.date;
    var byKey = {};
    (rel.downloads || []).forEach(function (x) { byKey[x.os + "-" + x.kind] = x; });
    Array.prototype.forEach.call(document.querySelectorAll("[data-dl]"), function (a) {
      var x = byKey[a.getAttribute("data-dl")];
      var u = x && safeUrl(x.url);
      if (u) {
        a.href = u;
        a.setAttribute("download", "");
        if (x.size) a.title = x.name + " (" + size(x.size) + ")";
      }
    });
    var cmd = document.getElementById("linux-cmd");
    var inst = byKey["linux-installer"];
    if (cmd && inst && safeUrl(inst.url)) cmd.textContent = "curl -fsSL " + inst.url + " | sudo bash";
    var body = document.getElementById("sums-body");
    (rel.downloads || []).forEach(function (x) {
      if (!x.sha256) return;
      var tr = document.createElement("tr");
      var a = document.createElement("td"); a.textContent = x.name;
      var b = document.createElement("td"); var c = document.createElement("code"); c.textContent = x.sha256; b.appendChild(c);
      tr.appendChild(a); tr.appendChild(b); body.appendChild(tr);
    });
  }).catch(function () {
    document.getElementById("release-line").textContent = "See the latest release on GitHub.";
  });
})();
