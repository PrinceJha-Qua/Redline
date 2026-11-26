"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => Number(n).toLocaleString("en-US");

  // The Varghese verdict, checked live when the store is reachable. The page carries Redline's real
  // output as its fallback, so it reads the same when hosted without a server.
  fetch("api/check", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: "Varghese v. China Southern Airlines Co., 925 F.3d 1339, 1345 (11th Cir. 2019)." }) })
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((d) => {
      const c = d.citations[0];
      if (c && c.verdict === "FABRICATED") { $("varghese").textContent = c.reason; $("live").classList.add("on"); }
    }).catch(() => {});

  fetch("api/coverage").then((r) => (r.ok ? r.json() : Promise.reject())).then((c) => {
    if (c.hosted) document.querySelector(".eyebrow").textContent = "Built on Relate by Neo4j · hosted demo · install it to run on your own machine";
    $("strip").textContent = `Relate directory store · read-only · ${fmt(c.cases)} cases · ${fmt(c.citations)} citations · ` +
      `${fmt(c.overrulings)} overrulings · ` + c.reporters.map((r) => `${r.abbr} ${r.first_year}–${r.last_year}`).join(" · ");
  }).catch(() => {});

  // The Chevron ripple: counters climb hop by hop, and dots fill each ring.
  const HOPS = [5082, 18224, 58574];
  const dots = $("dots"), NS = "http://www.w3.org/2000/svg";
  const rings = [[44, 98], [100, 158], [160, 186]];
  const per = [40, 90, 160];
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  rings.forEach(([r0, r1], h) => {
    for (let i = 0; i < per[h]; i++) {
      const a = rnd() * Math.PI * 2, r = r0 + rnd() * (r1 - r0);
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", (200 + r * Math.cos(a)).toFixed(1));
      c.setAttribute("cy", (200 + r * Math.sin(a)).toFixed(1));
      c.setAttribute("r", h === 0 ? 3 : 2.2);
      c.setAttribute("class", `dot h${h}`);
      dots.appendChild(c);
    }
  });
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function count(el, to, ms) {
    if (still) { el.textContent = fmt(to); return Promise.resolve(); }
    return new Promise((done) => {
      const t0 = performance.now();
      const step = (t) => {
        const p = Math.min(1, (t - t0) / ms);
        el.textContent = fmt(Math.round(to * (1 - Math.pow(1 - p, 3))));
        p < 1 ? requestAnimationFrame(step) : done();
      };
      requestAnimationFrame(step);
    });
  }
  let playing = false;
  async function play() {
    if (playing) return;
    playing = true;
    document.querySelectorAll(".dot").forEach((d) => d.classList.remove("on"));
    ["h1", "h2", "h3"].forEach((id) => ($(id).textContent = "0"));
    for (let h = 0; h < 3; h++) {
      const ds = [...document.querySelectorAll(`.dot.h${h}`)];
      ds.forEach((d, i) => setTimeout(() => d.classList.add("on"), still ? 0 : i * (900 / ds.length)));
      await count($(`h${h + 1}`), HOPS[h], 1000);
    }
    playing = false;
  }
  $("play").addEventListener("click", play);
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { play(); io.disconnect(); } },
      { threshold: 0.5 });
    io.observe($("ripple"));
  }
})();
