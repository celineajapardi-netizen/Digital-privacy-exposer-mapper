/*
 * SHADOW front-end.
 *
 * The browser does no analysis. It keeps track of which kinds of information
 * are ticked, asks the Python engine (POST /api/analyse) what that means, and
 * draws the answer: a force-directed graph (D3) plus the exposure panel.
 *
 * Sections:
 *   state        what is ticked and the example values typed in
 *   catalogue    the toggle list on the left
 *   graph        D3 force layout with object constancy (nodes keep their place)
 *   exposure     ring, "why" bullets, findings, trace, what-if, compare
 *   scenarios    save / load through the SQLite-backed API
 */

// ───────────────────────── state ─────────────────────────
const state = {
  catalogue: [],                 // [{key, label, category, sensitivity, description, example}]
  selected: new Set(),           // keys that are public
  values: {},                    // key -> example value typed by the user
  pinned: null,                  // {score, level, items} snapshot for before/after
  last: null,                    // the last analysis from the server
};

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const CATEGORY_ORDER = ["identity", "location", "routine", "social"];
const LEVEL_COLOR = {
  "Nothing shared": css("--lvl-none"),
  Low: css("--lvl-low"),
  Moderate: css("--lvl-moderate"),
  High: css("--lvl-high"),
  Severe: css("--lvl-severe"),
};
const SEVERITY_COLOR = { 1: css("--lvl-low"), 2: css("--lvl-moderate"), 3: css("--lvl-severe") };
const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (res.status === 204) return null;
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
}

// ───────────────────────── catalogue (left panel) ─────────────────────────
function renderCatalogue() {
  const root = $("catalogue");
  root.innerHTML = "";
  for (const category of CATEGORY_ORDER) {
    const group = document.createElement("div");
    group.className = "category";
    group.innerHTML = `<p class="category-name"><i style="--c:var(--${category})"></i>${category}</p>`;
    for (const info of state.catalogue.filter((i) => i.category === category)) {
      group.appendChild(renderItem(info));
    }
    root.appendChild(group);
  }
}

function renderItem(info) {
  const active = state.selected.has(info.key);
  const el = document.createElement("div");
  el.className = "item" + (active ? " active" : "");
  el.style.setProperty("--c", `var(--${info.category})`);
  el.dataset.key = info.key;
  el.innerHTML = `
    <span class="toggle" role="switch" aria-checked="${active}"></span>
    <span class="label">${info.label}</span>
    <span class="desc">${info.description}</span>
    ${active ? `<input placeholder="${info.example}" value="${state.values[info.key] || ""}" aria-label="Example ${info.label}">` : ""}
  `;
  el.addEventListener("click", (ev) => {
    if (ev.target.tagName === "INPUT") return;      // typing, not toggling
    toggle(info.key);
  });
  const input = el.querySelector("input");
  if (input) {
    input.addEventListener("input", () => {
      state.values[info.key] = input.value;
      updateNodeLabels();                           // live-update the label under the node
    });
  }
  return el;
}

function toggle(key) {
  if (state.selected.has(key)) state.selected.delete(key);
  else state.selected.add(key);
  renderCatalogue();
  refresh();
}

function setSelection(keys) {
  state.selected = new Set(keys);
  renderCatalogue();
  refresh();
}

// ───────────────────────── graph (D3) ─────────────────────────
const svg = d3.select("#graph");
const defs = svg.append("defs");
// soft glow for nodes
const glow = defs.append("filter").attr("id", "glow").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
glow.append("feGaussianBlur").attr("stdDeviation", 4).attr("result", "blur");
const merge = glow.append("feMerge");
merge.append("feMergeNode").attr("in", "blur");
merge.append("feMergeNode").attr("in", "SourceGraphic");

const linkLayer = svg.append("g").attr("class", "links");
const nodeLayer = svg.append("g").attr("class", "nodes");

let nodes = [];   // node objects, reused between updates so positions persist
let links = [];

const simulation = d3.forceSimulation()
  .force("link", d3.forceLink().id((d) => d.key).distance((l) => 170 - l.strength * 30))
  .force("charge", d3.forceManyBody().strength(-520))
  .force("collide", d3.forceCollide(52))
  .force("center", d3.forceCenter(0, 0))
  .on("tick", ticked);

function graphSize() {
  const r = svg.node().getBoundingClientRect();
  return { w: r.width, h: r.height };
}

new ResizeObserver(() => {
  const { w, h } = graphSize();
  simulation.force("center", d3.forceCenter(w / 2, h / 2));
  simulation.alpha(0.3).restart();
}).observe(svg.node());

const radius = (d) => 16 + d.sensitivity * 3;
const edgeId = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`);

function renderGraph(data) {
  const { w, h } = graphSize();
  $("graph-empty").hidden = data.items.length > 0;

  // Object constancy: keep the existing node object (with its x/y) for keys
  // that are still present; new nodes start near the centre.
  const previous = new Map(nodes.map((d) => [d.key, d]));
  nodes = data.items.map((item) =>
    Object.assign(previous.get(item.key) || { x: w / 2 + (Math.random() - 0.5) * 80, y: h / 2 + (Math.random() - 0.5) * 80 }, item),
  );
  links = data.edges.map((e) => ({ ...e }));

  const traceEdges = new Set();
  const traceNodes = new Set(data.trace ? data.trace.path : []);
  if (data.trace) {
    data.trace.path.forEach((k, i) => { if (i) traceEdges.add(edgeId(data.trace.path[i - 1], k)); });
  }

  // links
  linkLayer.selectAll("line")
    .data(links, (d) => edgeId(d.source.key ?? d.source, d.target.key ?? d.target))
    .join(
      (enter) => enter.append("line").attr("class", "link").attr("stroke-width", 0)
        .call((s) => s.transition().duration(400).attr("stroke-width", (d) => 1 + d.strength * 1.2)),
      (update) => update,
      (exit) => exit.transition().duration(250).attr("stroke-opacity", 0).remove(),
    )
    .attr("stroke-width", (d) => 1 + d.strength * 1.2)
    .classed("trace", (d) => traceEdges.has(edgeId(d.source.key ?? d.source, d.target.key ?? d.target)))
    .on("mousemove", (ev, d) => showTip(ev, `<b>${labelOf(d.source)} ↔ ${labelOf(d.target)}</b>${d.reason}`))
    .on("mouseleave", hideTip);

  // nodes
  const node = nodeLayer.selectAll("g.node")
    .data(nodes, (d) => d.key)
    .join(
      (enter) => {
        const g = enter.append("g").attr("class", "node").attr("opacity", 0);
        g.append("circle").attr("class", "halo").attr("r", (d) => radius(d) + 6);
        g.append("circle").attr("class", "body").attr("r", 0)
          .attr("fill", (d) => css(`--${d.category}`)).attr("fill-opacity", 0.22)
          .attr("stroke", (d) => css(`--${d.category}`)).attr("stroke-width", 2)
          .attr("filter", "url(#glow)");
        g.append("text").attr("class", "name").attr("dy", (d) => radius(d) + 16).text((d) => d.label);
        g.append("text").attr("class", "sub").attr("dy", (d) => radius(d) + 30);
        g.transition().duration(350).attr("opacity", 1);
        g.select("circle.body").transition().duration(350).attr("r", radius);
        return g;
      },
      (update) => update,
      (exit) => exit.transition().duration(250).attr("opacity", 0).remove(),
    )
    .classed("trace", (d) => traceNodes.has(d.key))
    .on("click", (ev, d) => toggle(d.key))
    .on("mousemove", (ev, d) => showTip(ev, `<b>${d.label}</b>${d.description}<br><span class="muted">sensitivity on its own: ${d.sensitivity}/3 · click to remove</span>`))
    .on("mouseleave", hideTip)
    .call(d3.drag()
      .on("start", (ev, d) => { if (!ev.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on("end", (ev, d) => { if (!ev.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));

  node.select("circle.halo").style("display", (d) => (traceNodes.has(d.key) ? null : "none"));
  updateNodeLabels();

  simulation.nodes(nodes);
  simulation.force("link").links(links);
  simulation.force("center", d3.forceCenter(w / 2, h / 2));
  simulation.alpha(0.8).restart();
}

function updateNodeLabels() {
  nodeLayer.selectAll("text.sub").text((d) => {
    const v = (state.values[d.key] || "").trim();
    return v.length > 22 ? v.slice(0, 21) + "…" : v;
  });
}

function ticked() {
  const { w, h } = graphSize();
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  nodeLayer.selectAll("g.node").attr("transform", (d) => {
    d.x = clamp(d.x, 40, w - 40);
    d.y = clamp(d.y, 40, h - 60);
    return `translate(${d.x},${d.y})`;
  });
  linkLayer.selectAll("line")
    .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
    .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
}

const labelOf = (n) => (typeof n === "string" ? state.catalogue.find((c) => c.key === n)?.label : n.label);

// Hovering a finding dims everything that is not part of it.
function highlight(keys, color) {
  const set = new Set(keys);
  nodeLayer.selectAll("g.node").classed("dimmed", (d) => set.size && !set.has(d.key));
  linkLayer.selectAll("line")
    .classed("dimmed", (d) => set.size && !(set.has(d.source.key) && set.has(d.target.key)))
    .style("stroke", (d) => (set.size && set.has(d.source.key) && set.has(d.target.key) ? color : null));
}

const tip = $("tooltip");
function showTip(ev, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  tip.style.left = `${ev.clientX + 14}px`;
  tip.style.top = `${ev.clientY + 14}px`;
}
function hideTip() { tip.hidden = true; }

// ───────────────────────── exposure (right panel) ─────────────────────────
const RING = 2 * Math.PI * 52;

function renderExposure(data) {
  const color = LEVEL_COLOR[data.level];
  $("level").textContent = data.level;
  $("level").style.color = color;
  $("ring").style.strokeDashoffset = RING * (1 - data.score / 100);
  $("ring").style.stroke = color;

  // count the score up/down rather than jumping
  const scoreEl = $("score");
  const from = +scoreEl.textContent || 0;
  d3.select(scoreEl).transition().duration(500).tween("n", () => {
    const i = d3.interpolateNumber(from, data.score);
    return (t) => { scoreEl.textContent = Math.round(i(t)); };
  });

  // before/after
  const cmp = $("compare");
  if (state.pinned) {
    const delta = data.score - state.pinned.score;
    cmp.hidden = false;
    cmp.innerHTML = `Before: <b>${state.pinned.level} (${state.pinned.score})</b> → now: <b>${data.level} (${data.score})</b>
      <span style="color:${delta > 0 ? css("--lvl-severe") : delta < 0 ? css("--lvl-low") : "inherit"}">${delta > 0 ? "+" : ""}${delta}</span>`;
  } else cmp.hidden = true;

  // why
  const b = data.breakdown;
  const why = [];
  if (b.items === 0) why.push("Nothing is public, so there is nothing to connect.");
  else {
    why.push(`${b.items} information point${b.items === 1 ? "" : "s"} shared`);
    why.push(`${b.relationships} relationship${b.relationships === 1 ? "" : "s"} detected${b.strong_relationships ? ` (${b.strong_relationships} strong)` : ""}`);
    why.push(`${b.findings} potentially sensitive combination${b.findings === 1 ? "" : "s"}${b.high_findings ? ` (${b.high_findings} high)` : ""}`);
    if (b.components > 1 && b.items > 1) why.push(`${b.components} separate clusters — these pieces are not yet linked to each other`);
    if (data.trace) why.push(`A stranger could trace from your ${labelOf(data.trace.path[0]).toLowerCase()} to your ${labelOf(data.trace.path.at(-1)).toLowerCase()}`);
  }
  $("why").innerHTML = why.map((w) => `<li>${w}</li>`).join("");

  // findings
  $("findings-count").textContent = data.findings.length ? `(${data.findings.length})` : "";
  const fl = $("findings");
  fl.innerHTML = data.findings.length ? "" : `<li class="muted">None yet. Combinations appear when pieces of information reinforce each other.</li>`;
  for (const f of data.findings) {
    const li = document.createElement("li");
    li.className = "finding";
    li.style.setProperty("--sev", SEVERITY_COLOR[f.severity]);
    li.innerHTML = `
      <div class="title"><span>${f.title}</span><span class="sev">${f.severity_label}</span></div>
      <div class="items">${f.items.map(labelOf).join(" + ")}</div>
      <div class="expl">${f.explanation}</div>`;
    li.addEventListener("mouseenter", () => highlight(f.items, SEVERITY_COLOR[f.severity]));
    li.addEventListener("mouseleave", () => highlight([]));
    fl.appendChild(li);
  }

  // trace
  const tr = $("trace");
  if (data.trace) {
    tr.innerHTML = `
      <p>${data.trace.summary}</p>
      <div class="chain">${data.trace.path.map(labelOf).map((l) => `<span>${l}</span>`).join("<i>→</i>")}</div>
      <ol>${data.trace.steps.map((s) => `<li>${s.reason}</li>`).join("")}</ol>`;
  } else {
    tr.innerHTML = `<p class="muted">No path from an online identity to a real place yet.</p>`;
  }

  // what-if
  renderWhatIf($("whatif-remove"), data.what_if.remove.filter((w) => w.delta < 0).slice(0, 4), "down", "Nothing to remove.");
  renderWhatIf($("whatif-add"), data.what_if.add.filter((w) => w.delta > 0).slice(0, 4), "up", "Everything is shared.");
}

function renderWhatIf(ul, list, dir, emptyText) {
  ul.innerHTML = list.length ? "" : `<li class="muted" style="cursor:default">${emptyText}</li>`;
  for (const w of list) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${w.label}<br><span class="to">→ ${w.level} (${w.score})</span></span>
                    <span class="delta ${dir}">${w.delta > 0 ? "+" : ""}${w.delta}</span>`;
    li.title = `Click to ${dir === "down" ? "remove" : "add"} ${w.label}`;
    li.addEventListener("click", () => toggle(w.key));
    ul.appendChild(li);
  }
}

// ───────────────────────── scenarios ─────────────────────────
async function renderScenarios() {
  const list = await api("/api/scenarios");
  const ul = $("scenarios");
  ul.innerHTML = list.length ? "" : `<li class="muted">None saved yet.</li>`;
  for (const s of list) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="name">${escapeHtml(s.name)}</span><span class="lvl">${s.level} (${s.score})</span>`;
    const load = document.createElement("button");
    load.textContent = "Load";
    load.addEventListener("click", () => setSelection(s.items));
    const del = document.createElement("button");
    del.textContent = "✕";
    del.addEventListener("click", async () => { await api(`/api/scenarios/${s.id}`, { method: "DELETE" }); renderScenarios(); });
    li.append(load, del);
    ul.appendChild(li);
  }
}

const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ───────────────────────── wiring ─────────────────────────
async function refresh() {
  const data = await api("/api/analyse", { method: "POST", body: JSON.stringify({ items: [...state.selected] }) });
  state.last = data;
  renderGraph(data);
  renderExposure(data);
}

$("presets").addEventListener("click", (ev) => {
  const btn = ev.target.closest("button");
  if (!btn) return;
  const p = btn.dataset.preset;
  setSelection(p === "all" ? state.catalogue.map((c) => c.key) : p ? p.split(",") : []);
});

$("pin").addEventListener("click", () => {
  if (!state.last) return;
  state.pinned = { score: state.last.score, level: state.last.level, items: [...state.selected] };
  $("unpin").hidden = false;
  renderExposure(state.last);
});
$("unpin").addEventListener("click", () => {
  state.pinned = null;
  $("unpin").hidden = true;
  renderExposure(state.last);
});

$("save-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  await api("/api/scenarios", { method: "POST", body: JSON.stringify({ name: $("save-name").value, items: [...state.selected] }) });
  $("save-name").value = "";
  renderScenarios();
});

(async function init() {
  state.catalogue = await api("/api/catalogue");
  renderCatalogue();
  await refresh();
  renderScenarios();
})();
