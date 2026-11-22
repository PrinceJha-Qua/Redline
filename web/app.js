"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const text = $("text"), doc = $("doc"), list = $("list"), summary = $("summary");
  const checkBtn = $("check"), editBtn = $("edit"), hint = $("hint");
  const detail = $("detail"), detailBody = $("detail-body"), empty = $("empty");
  let result = null, selected = -1;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n).toLocaleString("en-US");

  function kind(c) {
    if (c.verdict === "FABRICATED") return "fab";
    if (c.verdict === "UNVERIFIABLE") return "unk";
    if (c.status === "overruled" || c.status === "overruled in part") return "ovr";
    if (c.status === "caution") return "cau";
    return "ok";
  }
  const VERDICT_CHIP = { FABRICATED: "v-fab", VERIFIED: "v-ok", UNVERIFIABLE: "v-unk" };
  const STATUS_CHIP = { overruled: "s-ovr", "overruled in part": "s-ovr", caution: "s-cau", "good law": "s-good" };
  const chip = (cls, label) => `<span class="chip ${cls}">${esc(label)}</span>`;

  // ---- store line -------------------------------------------------------------------------
  fetch("/api/coverage").then((r) => r.json()).then((c) => {
    const where = c.store.split(/[\\/]/).slice(-2).join("/");
    $("store").textContent = `Relate store ${where} · ${fmt(c.cases)} cases · ${fmt(c.citations)} citations · ` +
      c.reporters.map((r) => `${r.abbr} ${r.first_year}–${r.last_year}`).join(", ");
  }).catch(() => { $("store").textContent = "Store not reachable. Start it with `make run`."; });

  // ---- samples ----------------------------------------------------------------------------
  const samples = window.REDLINE_SAMPLES || [];
  function pickSample(id) {
    const s = samples.find((x) => x.id === id);
    if (!s) return;
    for (const b of $("samples").children) b.setAttribute("aria-pressed", String(b.dataset.id === id));
    text.value = s.text;
    run();
  }
  for (const s of samples) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = s.label; b.dataset.id = s.id; b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => pickSample(s.id));
    $("samples").appendChild(b);
  }

  // ---- check ------------------------------------------------------------------------------
  async function run() {
    const body = text.value;
    if (!body.trim()) { hint.textContent = "Paste a brief first."; return; }
    checkBtn.disabled = true; checkBtn.textContent = "Checking…";
    const started = performance.now();
    try {
      const r = await fetch("/api/check", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: body }) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `The check failed (${r.status}).`);
      result = { text: body, ...data };
      const ms = Math.round(performance.now() - started);
      hint.textContent = `Checked ${data.summary.citations} citation${data.summary.citations === 1 ? "" : "s"} in ${ms} ms, on this machine.`;
      render();
      const first = data.citations.findIndex((c) => kind(c) === "fab");
      select(first >= 0 ? first : (data.citations.length ? 0 : -1));
    } catch (e) {
      hint.textContent = e.message || "The check failed. Is the server running?";
    } finally {
      checkBtn.disabled = false; checkBtn.textContent = "Check citations";
    }
  }

  function render() {
    const s = result.summary;
    summary.innerHTML = [
      s.fabricated ? chip("v-fab", `${s.fabricated} fabricated`) : "",
      s.overruled ? chip("s-ovr", `${s.overruled} overruled`) : "",
      s.caution ? chip("s-cau", `${s.caution} caution`) : "",
      chip("v-ok", `${s.verified} verified`),
      s.unverifiable ? chip("v-unk", `${s.unverifiable} unverifiable`) : "",
    ].join("");

    // the document with each citation marked in place
    let html = "", at = 0;
    result.citations.forEach((c, i) => {
      const [a, b] = c.span;
      if (a < at) return;
      html += esc(result.text.slice(at, a)) +
        `<span class="cite ${kind(c)}" data-i="${i}" tabindex="0" role="button" aria-label="${esc(c.text)}: ${esc(c.verdict.toLowerCase())}">${esc(result.text.slice(a, b))}</span>`;
      at = b;
    });
    doc.innerHTML = html + esc(result.text.slice(at));
    text.hidden = true; doc.hidden = false; editBtn.hidden = false;

    list.innerHTML = result.citations.map((c, i) => `
      <li><button class="item ${kind(c)}" data-i="${i}" type="button">
        <span class="item-top">${chip(VERDICT_CHIP[c.verdict], c.verdict.toLowerCase())}
          ${c.status ? chip(STATUS_CHIP[c.status] || "v-ok", c.status) : ""}
          <span class="item-cite">${esc(c.text)}</span></span>
        ${c.name ? `<span class="item-name">${esc(c.name)}</span>` : ""}
        <span class="item-reason">${esc(c.reason)}</span>
      </button></li>`).join("");
    empty.hidden = result.citations.length > 0;
    if (!result.citations.length) empty.querySelector("p").textContent = "No case citations found in this text.";
  }

  function select(i) {
    selected = i;
    document.querySelectorAll(".cite.sel, .item.sel").forEach((el) => el.classList.remove("sel"));
    if (i < 0) { detail.hidden = true; return; }
    document.querySelectorAll(`[data-i="${i}"]`).forEach((el) => el.classList.add("sel"));
    const span = doc.querySelector(`.cite[data-i="${i}"]`);
    if (span) span.scrollIntoView({ block: "nearest", behavior: "smooth" });
    showDetail(result.citations[i]);
  }

  // ---- evidence ---------------------------------------------------------------------------
  function showDetail(c) {
    const parts = [];
    parts.push(`<div class="item-top">${chip(VERDICT_CHIP[c.verdict], c.verdict.toLowerCase())}
      ${c.status ? chip(STATUS_CHIP[c.status] || "v-ok", c.status) : ""}<span class="item-cite">${esc(c.text)}</span></div>`);
    parts.push(`<p class="reason">${esc(c.reason)}</p>`);
    for (const w of c.warnings || []) parts.push(`<p class="warn">${esc(w)}</p>`);
    if (c.evidence && c.evidence.nodes.length) parts.push(`<div class="graph">${graph(c)}</div>`);
    if (c.stands_on && c.stands_on.length) {
      parts.push(`<div class="k">What it stands on${c.stands_on_total > c.stands_on.length ? ` (top ${c.stands_on.length} of ${c.stands_on_total})` : ""}</div>`);
      parts.push(`<ol class="chain">${c.stands_on.map((ch) => `
        <li><span><b>${esc(ch.case.name)}</b>, ${esc(ch.case.cite)} (${esc(ch.case.year)}), cited ${esc(ch.weight)}×</span>
        ${ch.parenthetical ? `<span class="paren">“${esc(ch.parenthetical)}”</span>` : ""}
        <span>${chip("s-ovr", ch.case.status)} by ${esc(ch.overruled_by.name)} (${esc(ch.overruled_by.year)})</span></li>`).join("")}</ol>`);
    }
    if (c.mentions && c.mentions.length) {
      parts.push(`<div class="k">Mentioned in passing, not relied on</div>`);
      parts.push(`<ul class="mentions">${c.mentions.map((m) => `
        <li>${esc(m.case.name)}, ${esc(m.case.cite)}: later overruled by ${esc(m.overruled_by.name)} (${esc(m.overruled_by.year)})</li>`).join("")}</ul>`);
    }
    if (c.case) parts.push(`<div><button class="case-link" type="button" data-case="${esc(c.case.id)}">Open ${esc(c.case.name)} in the graph</button></div><div id="case-box"></div>`);
    if (c.evidence && c.evidence.query) {
      parts.push(`<details class="cypher"><summary>The Cypher behind this verdict</summary><pre>${esc(c.evidence.query.cypher)}\n\n// params ${esc(JSON.stringify(c.evidence.query.params))}</pre></details>`);
    }
    detailBody.innerHTML = parts.join("");
    detail.hidden = false;
  }

  function openCase(id) {
    const box = $("case-box");
    if (!box) return;
    box.innerHTML = `<p class="hint">Loading…</p>`;
    fetch(`/api/case/${encodeURIComponent(id)}`).then((r) => r.json()).then((d) => {
      const k = d.case;
      box.innerHTML = `<div class="stats"><span>${esc(k.court_name || k.court)}</span><span>decided ${esc(k.date || k.year)}</span>
        ${k.cited_by ? `<span>cited by ${fmt(k.cited_by)} cases in this store</span>` : ""}
        ${k.authority ? `<span>authority ${Number(k.authority).toFixed(3)}</span>` : ""}</div>
        ${d.cited_by.length ? `<div class="k" style="margin-top:10px">Most reliant citing cases</div><ol class="chain">${d.cited_by.slice(0, 5).map((f) => `
          <li><span><b>${esc(f.name)}</b>, ${esc(f.cite)} (${esc(f.court)} ${esc(f.year)}), cited ${esc(f.weight)}×</span>
          ${f.parenthetical ? `<span class="paren">“${esc(f.parenthetical)}”</span>` : ""}</li>`).join("")}</ol>` : ""}`;
    }).catch(() => { box.innerHTML = `<p class="warn">Could not load that case.</p>`; });
  }

  // A small layered drawing: brief → cited case (or volume) → what it rests on → what overruled it.
  function graph(c) {
    const ev = c.evidence, k = kind(c);
    const nodes = [{ id: "__brief", label: "Your brief", sub: c.text, role: "brief" }].concat(
      ev.nodes.map((n) => ({ id: n.id, label: n.label, sub: n.cite + (n.year ? ` (${n.year})` : ""), role: n.role })));
    const edges = [{ source: "__brief", target: (ev.nodes.find((n) => n.role === "cited" || n.role === "volume") || {}).id,
      type: k === "fab" ? "POINTS TO" : "CITES" }].concat(ev.edges).filter((e) => e.target);
    const citedId = (ev.nodes.find((n) => n.role === "cited") || {}).id;
    const col = (n) => {
      if (n.role === "brief") return 0;
      if (n.role === "cited" || n.role === "volume") return 1;
      if (n.role === "overruling") return ev.edges.some((e) => e.source === n.id && e.target === citedId) ? 2 : 3;
      return 2;
    };
    const cols = {};
    for (const n of nodes) { n.col = col(n); n.row = (cols[n.col] = (cols[n.col] || 0) + 1) - 1; }
    const W = 176, H = 48, GX = 84, GY = 18, P = 16;
    const ncols = Math.max(...nodes.map((n) => n.col)) + 1, nrows = Math.max(...Object.values(cols));
    const width = P * 2 + ncols * W + (ncols - 1) * GX, height = P * 2 + nrows * H + (nrows - 1) * GY + 8;
    const pos = {};
    for (const n of nodes) {
      const colRows = cols[n.col], offset = ((nrows - colRows) * (H + GY)) / 2;
      pos[n.id] = { x: P + n.col * (W + GX), y: P + offset + n.row * (H + GY), n };
    }
    const stroke = (n) => ({ brief: "var(--ink)", cited: { fab: "var(--red)", ovr: "var(--red)", cau: "var(--amber)", ok: "var(--green)", unk: "var(--grey)" }[k],
      volume: "var(--grey)", actual: "var(--ink)", overruled: "var(--red)", overruling: "var(--ink)" }[n.role] || "var(--muted)");
    const trim = (s, m) => (s && s.length > m ? s.slice(0, m - 1) + "…" : s || "");
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Evidence graph for ${esc(c.text)}">
      <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="var(--muted)"/></marker>
      <marker id="arr-r" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="var(--red)"/></marker></defs>`;
    for (const e of edges) {
      const a = pos[e.source], b = pos[e.target];
      if (!a || !b) continue;
      const forward = a.x < b.x;
      const x1 = forward ? a.x + W : a.x, x2 = forward ? b.x : b.x + W;
      const y1 = a.y + H / 2, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
      const ovr = e.type === "OVERRULES";
      svg += `<path class="edge${ovr ? " ovr" : ""}" d="M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}" marker-end="url(#${ovr ? "arr-r" : "arr"})"/>`;
      svg += `<text class="elbl" x="${mx}" y="${(y1 + y2) / 2 - 5}" text-anchor="middle">${esc(e.type)}</text>`;
    }
    for (const id in pos) {
      const { x, y, n } = pos[id];
      svg += `<g><rect x="${x}" y="${y}" width="${W}" height="${H}" rx="7" fill="var(--panel)" stroke="${stroke(n)}" stroke-width="${n.role === "cited" || n.role === "volume" ? 2 : 1.4}"/>
        <text class="lbl" x="${x + 10}" y="${y + 20}">${esc(trim(n.label, 25))}</text>
        <text class="sub" x="${x + 10}" y="${y + 37}">${esc(trim(n.sub, 28))}</text><title>${esc(n.label)} · ${esc(n.sub)}</title></g>`;
    }
    return svg + "</svg>";
  }

  // ---- events -----------------------------------------------------------------------------
  checkBtn.addEventListener("click", run);
  editBtn.addEventListener("click", () => {
    doc.hidden = true; text.hidden = false; editBtn.hidden = true; text.focus();
  });
  text.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run(); });
  const pick = (e) => {
    const el = e.target.closest("[data-i]");
    if (el) select(Number(el.dataset.i));
  };
  doc.addEventListener("click", pick);
  doc.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(e); } });
  list.addEventListener("click", pick);
  detailBody.addEventListener("click", (e) => {
    const b = e.target.closest("[data-case]");
    if (b) openCase(b.dataset.case);
  });
  $("close").addEventListener("click", () => select(-1));

  pickSample("demo");
})();
