/* Public snapshot viewer. Browser controls are an unsaved local preview. */
"use strict";
const DIMS = [
  ["audience_relevance", "Audience relevance"], ["engagement", "Engagement"],
  ["brand_fit", "Brand fit"], ["momentum", "Momentum"],
  ["speed_to_activate", "Speed to activate"], ["trend_fit", "Trend fit"]
];
const CAPS = ["reach", "demonstration", "credibility", "speed"];
function fit(c, weights) {
  let total = 0, sum = 0;
  for (const [key] of DIMS) {
    const score = c.d[key].s, w = weights[key] ?? 0;
    if (score != null) { total += score * w; sum += w; }
  }
  return sum ? Math.round(total / sum * 10000) / 10000 : null;
}
function components(c, score, priorities, selected) {
  const quality = score / 10;
  if (!selected.length) return {quality, coverage_gain: 0, max_similarity: 0, total: quality, selection_rule: "quality_anchor"};
  const total = CAPS.reduce((sum, k) => sum + priorities[k], 0);
  const gain = total ? CAPS.reduce((sum, k) => sum + priorities[k] * Math.max(
    0, (c.capabilities?.[k] ?? 0) - Math.max(...selected.map(p => p.c.capabilities?.[k] ?? 0))
  ), 0) / total : 0;
  const similarity = Math.max(...selected.map(p => c.similarity?.[p.c.h] ?? 0));
  return {quality, coverage_gain: gain, max_similarity: similarity,
    total: .5 * quality + .35 * gain - .15 * similarity, selection_rule: "marginal_teammate"};
}
function ranked(data, weights, dropped = new Set()) {
  return data.filter(c => !dropped.has(c.h) && c.safety !== "FAIL")
    .map(c => ({c, score: fit(c, weights)})).filter(x => x.score != null)
    .sort((a, b) => b.score - a.score || (a.c.h < b.c.h ? -1 : a.c.h > b.c.h ? 1 : 0));
}
function selectRoster(rows, priorities) {
  const left = [...rows], selected = [];
  while (left.length && selected.length < 4) {
    let index = 0, value = -Infinity;
    left.forEach((r, i) => { const score = components(r.c, r.score, priorities, selected).total;
      if (score > value) { index = i; value = score; } });
    const item = left.splice(index, 1)[0];
    item.components = components(item.c, item.score, priorities, selected);
    selected.push(item);
  }
  return selected;
}
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
if (typeof module !== "undefined") module.exports = {fit, components, ranked, selectRoster, esc};
if (typeof document !== "undefined") {
  const exported = typeof DATA !== "undefined" && typeof RUN !== "undefined";
  const data = exported ? DATA : FALLBACK_DATA;
  const run = exported ? RUN : null;
  const defaults = run?.weights ?? Object.fromEntries(DIMS.map(([k]) => [k, 1 / 6]));
  const priorities = run?.priorities ?? Object.fromEntries(CAPS.map(k => [k, 0]));
  let weights = {...defaults}, edited = false;
  const dropped = new Set(), opened = new Set();
  document.getElementById("run-status").textContent = run
    ? (run.mode === "live" ? "Live-data snapshot" : "SYNTHETIC DEMO") + " | " + run.snapshot_at + " | Run " + run.run_id + " | " + run.scoring_version
    : "Export unavailable. Showing historical fallback data, not a current pipeline run.";
  document.getElementById("fact-candidates").textContent = data.length;
  document.getElementById("run-warnings").textContent = run?.warnings.join(" ") ?? "Fallback has incomplete scores and no saved balanced roster.";
  function render() {
    const rows = ranked(data, weights, dropped), selected = !edited && run
      ? run.roster.map(p => ({c: data.find(c => c.h === p.handle),
          score: data.find(c => c.h === p.handle)?.score, components: p.components})).filter(p => p.c)
      : selectRoster(rows, priorities);
    const ids = new Set(selected.map(p => p.c.h));
    document.getElementById("roles").innerHTML = selected.map((p, i) => {
      const capabilities = Object.entries(p.c.capabilities ?? {});
      const role = capabilities.sort((a, b) => b[1] - a[1])[0]?.[0] ?? "Unassigned";
      const individual = rows.findIndex(r => r.c.h === p.c.h) + 1;
      return '<div class="role" style="--rc:#2E6BB8"><div class="rname">Pick ' + (i+1) + ' · ' + esc(role) +
        '</div><div class="rcast">' + esc(p.c.h) + '</div><div class="rwhy">Individual rank #' + individual +
        ' · ' + p.score.toFixed(2) + '/10<br>Added coverage: ' + p.components.coverage_gain.toFixed(3) +
        '<br>' + (i ? "Best teammate at this step" : "Best individual quality first") + '</div></div>';
    }).join("");
    document.getElementById("count").textContent = rows.length + " ranked";
    document.getElementById("list").innerHTML = rows.map(({c, score}, i) => {
      const isOpen = opened.has(c.h);
      const bars = DIMS.map(([k, label]) => c.d[k].s == null
        ? '<div class="bar null" title="' + label + ': not measured"></div>'
        : '<div class="bar" title="' + label + ': ' + c.d[k].s.toFixed(2) + '"><i style="height:' + Math.max(6, c.d[k].s*3) + 'px"></i></div>').join("");
      const reasons = isOpen ? '<div class="why">' + DIMS.map(([k, label]) =>
        '<div><b>' + label + ':</b> ' + (c.d[k].s == null ? "not measured" : c.d[k].s.toFixed(2) + "/10") + ' — ' + esc(c.d[k].r) + '</div>').join("") + '</div>' : "";
      return '<li class="item' + (ids.has(c.h) ? " cast" : "") + '"><div class="rank">' + (i+1) +
        '</div><div class="who"><div class="handle">' + esc(c.h) +
        '</div><div class="meta">' + esc(c.t) + ' · ' + (c.subs == null ? "Subscribers unavailable" : c.subs.toLocaleString() + " subscribers") +
        ' · ' + esc(c.safety ?? "Historical data") + '</div></div><div class="bars">' + bars +
        '</div><div class="right"><div class="score">' + score.toFixed(2) +
        '<small>WEIGHTED</small></div></div><div style="grid-column:1/-1;display:flex;gap:8px">' +
        '<button class="act" data-why="' + esc(c.h) + '">' + (isOpen ? "Hide reasons" : "Why this score") +
        '</button><button class="act" data-drop="' + esc(c.h) + '">Remove in preview</button></div>' + reasons + '</li>';
    }).join("");
    document.getElementById("meter").textContent = edited
      ? "Local preview — weights/removals are not saved to the backend. Export a new backend run to publish changes."
      : run ? "Showing the exact saved backend roster. Slider changes create a local preview; no API calls." : "Historical fallback preview; no saved run is loaded.";
  }
  function controls() {
    document.getElementById("presets").innerHTML = '<button class="chip" id="restore-run">Restore saved run</button>';
    document.getElementById("sliders").innerHTML = DIMS.map(([k, label]) =>
      '<div class="slider"><div class="slabel"><b>' + label + '</b><span id="v-' + k + '">' + (weights[k]*100).toFixed(0) +
      '%</span></div><input type="range" id="w-' + k + '" min="0" max="1" step="0.01" value="' + weights[k] + '"></div>').join("");
  }
  document.addEventListener("input", e => {
    if (!e.target.id?.startsWith("w-")) return;
    const k = e.target.id.slice(2); weights[k] = Number(e.target.value); edited = true;
    document.getElementById("v-" + k).textContent = (weights[k]*100).toFixed(0) + "%"; render();
  });
  document.addEventListener("click", e => {
    const why = e.target.closest("[data-why]"), drop = e.target.closest("[data-drop]");
    if (why) { const h = why.dataset.why; opened.has(h) ? opened.delete(h) : opened.add(h); render(); }
    if (drop) { dropped.add(drop.dataset.drop); edited = true; render(); }
    if (e.target.closest("#restore-run")) { weights = {...defaults}; dropped.clear(); edited = false; controls(); render(); }
  });
  controls(); render();
}
