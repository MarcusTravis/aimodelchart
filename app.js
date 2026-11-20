(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var state = { models: [], sort: "pop_rank", dir: 1, maker: null };
  var DASH = "—";

  function num(v, d) { return v == null ? DASH : Number(v).toLocaleString("en-US", { maximumFractionDigits: d || 0, minimumFractionDigits: d || 0 }); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function cmp(a, b) {
    var k = state.sort, x = a[k], y = b[k];
    if (x == null && y == null) return 0;
    if (x == null) return 1;      // missing values always last
    if (y == null) return -1;
    var r = typeof x === "string" ? x.localeCompare(y) : x - y;
    return r * state.dir;
  }
  // natural direction: ranks ascending, scores descending
  var DESC_FIRST = { share: 1, eci: 1, arena: 1, rank_change: 1 };

  function render() {
    var list = state.models.filter(function (m) { return !state.maker || m.maker === state.maker; }).sort(cmp);
    var maxShare = Math.max.apply(null, state.models.map(function (m) { return m.share || 0; }).concat([0.0001]));
    var tb = $("rows"); tb.textContent = "";
    list.forEach(function (m) {
      var tr = el("tr");
      tr.appendChild(el("td", m.pop_rank ? "" : "muted", m.pop_rank || DASH));
      var n = el("td", "name left", m.name);
      if (m.access) n.appendChild(el("small", "", m.access));
      tr.appendChild(n);
      tr.appendChild(el("td", "left muted hide-sm", m.maker || DASH));
      var s = el("td");
      if (m.share != null) {
        var w = el("span", "share"); w.appendChild(el("span", "", (m.share * 100).toFixed(1) + "%"));
        var bar = el("i"); bar.style.width = Math.max(2, Math.round(m.share / maxShare * 70)) + "px"; w.appendChild(bar); s.appendChild(w);
      } else { s.className = "muted"; s.textContent = DASH; }
      tr.appendChild(s);
      var c = el("td", "hide-sm");
      if (m.new_entry) { c.textContent = "new"; c.className += " muted"; }
      else if (m.rank_change == null) { c.textContent = DASH; c.className += " muted"; }
      else if (m.rank_change > 0) { c.textContent = "▲ " + m.rank_change; c.className += " up"; }
      else if (m.rank_change < 0) { c.textContent = "▼ " + Math.abs(m.rank_change); c.className += " down"; }
      else { c.textContent = "="; c.className += " muted"; }
      tr.appendChild(c);
      tr.appendChild(el("td", m.eci == null ? "muted" : "", num(m.eci, 1)));
      tr.appendChild(el("td", m.arena == null ? "muted" : "", num(m.arena)));
      tr.appendChild(el("td", "hide-sm " + (m.arena_rank == null ? "muted" : ""), m.arena_rank == null ? DASH : m.arena_rank));
      tb.appendChild(tr);
    });
    document.querySelectorAll("#tbl th").forEach(function (th) {
      if (th.dataset.k === state.sort) th.setAttribute("aria-sort", state.dir > 0 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
  }

  function chips() {
    var makers = {};
    state.models.forEach(function (m) { if (m.maker) makers[m.maker] = (makers[m.maker] || 0) + 1; });
    var names = Object.keys(makers).sort(function (a, b) { return makers[b] - makers[a] || a.localeCompare(b); });
    var box = $("chips"); box.textContent = "";
    [null].concat(names).forEach(function (n) {
      var b = el("button", "chip", n || "All"); b.type = "button";
      b.setAttribute("aria-pressed", String(state.maker === n));
      b.onclick = function () { state.maker = n; chips(); render(); };
      box.appendChild(b);
    });
  }

  function scatter() {
    var pts = state.models.filter(function (m) { return m.pop_rank && m.eci; });
    var box = $("scatter"); box.textContent = "";
    if (pts.length < 3) { $("chart-card").hidden = true; return; }
    var W = 800, H = 360, L = 44, R = 16, T = 12, B = 34, NS = "http://www.w3.org/2000/svg";
    var maxR = Math.max.apply(null, pts.map(function (m) { return m.pop_rank; }));
    var es = pts.map(function (m) { return m.eci; }), lo = Math.floor(Math.min.apply(null, es) / 10) * 10, hi = Math.ceil(Math.max.apply(null, es) / 10) * 10;
    function X(r) { return L + (maxR - r) / Math.max(1, maxR - 1) * (W - L - R); }
    function Y(e) { return T + (hi - e) / (hi - lo) * (H - T - B); }
    var svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    function add(tag, attrs, text) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; svg.appendChild(e); return e; }
    for (var v = lo; v <= hi; v += 10) { add("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v) }); add("text", { x: L - 6, y: Y(v) + 4, "text-anchor": "end" }, v); }
    add("text", { x: L, y: H - 10 }, "Less used"); add("text", { x: W - R, y: H - 10, "text-anchor": "end" }, "More used");
    var top = pts.slice().sort(function (a, b) { return b.eci - a.eci; }).slice(0, 6).concat(pts.filter(function (m) { return m.pop_rank <= 3; }));
    pts.forEach(function (m) {
      var c = add("circle", { cx: X(m.pop_rank), cy: Y(m.eci), r: 5, class: m.access === "Open" ? "dot open" : "dot" });
      var t = document.createElementNS(NS, "title"); t.textContent = m.name + " — #" + m.pop_rank + ", ECI " + m.eci; c.appendChild(t);
      if (top.indexOf(m) >= 0) add("text", { x: X(m.pop_rank) + 8, y: Y(m.eci) + 4, class: "lbl" }, m.name);
    });
    box.appendChild(svg);
    box.appendChild(el("p", "note", "Blue: closed weights. Gray: open weights."));
  }

  function init(d) {
    state.models = d.models || [];
    var s = d.sources || {};
    if (d.generated_at) {
      var dt = new Date(d.generated_at);
      $("updated").textContent = "Last updated " + dt.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" }) + " UTC";
    } else $("updated").textContent = "";
    if (s.openrouter) $("credit-or").textContent = s.openrouter.credit;
    if (s.eci) $("credit-eci").textContent = s.eci.credit + (s.eci.as_of ? " Fetched " + s.eci.as_of + "." : "");
    if (s.arena) $("credit-arena").textContent = s.arena.credit + (s.arena.as_of ? " Published " + s.arena.as_of + "." : "");
    if (!state.models.length) { fail("No model data yet."); return; }
    if (!state.models.some(function (m) { return m.pop_rank; })) {
      state.sort = "eci"; state.dir = -1;
      var st = $("state"); st.hidden = false; st.textContent = "Popularity data is temporarily unavailable; showing models by Epoch ECI.";
    }
    chips(); render(); scatter();
  }

  function fail(msg) {
    $("updated").textContent = "";
    var st = $("state"); st.hidden = false; st.textContent = msg;
  }

  document.querySelectorAll("#tbl th").forEach(function (th) {
    th.querySelector("button").onclick = function () {
      var k = th.dataset.k;
      if (state.sort === k) state.dir = -state.dir; else { state.sort = k; state.dir = DESC_FIRST[k] ? -1 : 1; }
      render();
    };
  });

  fetch("./data/latest.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch(function () { fail("Couldn’t load the data. Please try again shortly."); });
})();
